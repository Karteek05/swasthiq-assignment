import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class ToolArgumentError(ValueError):
    """Raised for malformed/invalid tool arguments. Distinct from ValueError
    used for valid-but-unsatisfiable requests (e.g. slot taken), so callers
    can tell "you asked wrong" apart from "that can't be done right now"."""


def _require(value: Any, field: str) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ToolArgumentError(f"'{field}' is required and was missing or empty.")
    return value


def _require_date(value: Any, field: str = "date") -> str:
    _require(value, field)
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise ToolArgumentError(f"'{field}' must be in YYYY-MM-DD format, got {value!r}.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ToolArgumentError(f"'{field}' is not a real calendar date: {value!r}.")
    return value


def _require_time(value: Any, field: str = "start") -> str:
    _require(value, field)
    if not isinstance(value, str) or not TIME_RE.match(value):
        raise ToolArgumentError(f"'{field}' must be in HH:MM 24-hour format, got {value!r}.")
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ToolArgumentError(f"'{field}' is not a real time of day: {value!r}.")
    return value


class ClinicState:
    def __init__(self, data_path: str = "clinic.json"):
        with open(data_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        # Guards the check-then-write window in book/reschedule so two
        # concurrent calls against the same ClinicState can't both claim
        # the same slot (TOCTOU race).
        self._lock = threading.Lock()

    def _get_day_of_week(self, date_str: str) -> str:
        # returns Mon, Tue, Wed, Thu, Fri, Sat, Sun
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%a")

    def lookup_patient(self, query: str) -> List[Dict[str, Any]]:
        _require(query, "query")
        q = query.lower().strip()
        candidates = []
        for p in self.data["patients"]:
            if q in p["name"].lower() or q in p["phone"]:
                # Surface the patient's own booked appointments alongside
                # their identity. None of the six tools otherwise let the
                # agent discover an appointment_id for "my appointment
                # today" - without this, reschedule/cancel of an
                # unspecified appointment is impossible without guessing
                # an id (an invented fact). This is still 100% grounded:
                # it's the same clinic.json data, just attached here.
                appointments = [
                    ap for ap in self.data["appointments"]
                    if ap["patient_id"] == p["id"] and ap["status"] == "booked"
                ]
                candidates.append({**p, "appointments": appointments})
        return candidates

    def get_patient(self, patient_id: str) -> Dict[str, Any]:
        for p in self.data["patients"]:
            if p["id"] == patient_id:
                return p
        return None

    def _get_doctor(self, doctor_id: str) -> Dict[str, Any]:
        for d in self.data["doctors"]:
            if d["id"] == doctor_id:
                return d
        return None

    def _require_doctor(self, doctor_id: str) -> Dict[str, Any]:
        _require(doctor_id, "doctor_id")
        doctor = self._get_doctor(doctor_id)
        if not doctor:
            raise ToolArgumentError(f"No doctor with id {doctor_id!r}.")
        return doctor

    def search_slots(self, doctor_id: str, date_str: str) -> List[str]:
        doctor = self._require_doctor(doctor_id)
        _require_date(date_str)

        if date_str in self.data["holidays"]:
            return []

        if date_str in doctor["leave_dates"]:
            return []

        day_of_week = self._get_day_of_week(date_str)

        # generate all slots (dedup: a doctor's windows can overlap, e.g.
        # dr_rao's Monday 09:00-12:00 and 11:45-15:00 windows overlap by
        # 15 minutes in the source data — see DECISIONS.md)
        slots = set()
        slot_minutes = self.data["clinic"]["slot_minutes"]

        for w in doctor["windows"]:
            if w["day"] == day_of_week:
                start_dt = datetime.strptime(f"{date_str} {w['start']}", "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(f"{date_str} {w['end']}", "%Y-%m-%d %H:%M")

                curr = start_dt
                while curr + timedelta(minutes=slot_minutes) <= end_dt:
                    slots.add(curr.strftime("%H:%M"))
                    curr += timedelta(minutes=slot_minutes)

        # remove booked slots
        booked_slots = set()
        for ap in self.data["appointments"]:
            if ap["doctor_id"] == doctor_id and ap["date"] == date_str and ap["status"] == "booked":
                booked_slots.add(ap["start"])

        return sorted(s for s in slots if s not in booked_slots)

    def book_appointment(self, patient_id: str, doctor_id: str, date_str: str, start_time: str) -> Dict[str, Any]:
        _require(patient_id, "patient_id")
        self._require_doctor(doctor_id)
        _require_date(date_str)
        _require_time(start_time, "start")

        if not self.get_patient(patient_id):
            raise ToolArgumentError(f"No patient with id {patient_id!r}.")

        with self._lock:
            slots = self.search_slots(doctor_id, date_str)
            if start_time not in slots:
                raise ValueError(f"Slot {start_time} on {date_str} is not available for doctor {doctor_id}.")

            start_dt = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=self.data["clinic"]["slot_minutes"])

            ap_id = f"ap_{uuid.uuid4().hex[:8]}"
            ap = {
                "id": ap_id,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "date": date_str,
                "start": start_time,
                "end": end_dt.strftime("%H:%M"),
                "status": "booked"
            }
            self.data["appointments"].append(ap)
            return ap

    def _find_appointment(self, appointment_id: str) -> Dict[str, Any]:
        _require(appointment_id, "appointment_id")
        for ap in self.data["appointments"]:
            if ap["id"] == appointment_id:
                return ap
        raise ValueError(f"Appointment {appointment_id} not found.")

    def cancel_appointment(self, appointment_id: str) -> bool:
        ap = self._find_appointment(appointment_id)
        with self._lock:
            if ap["status"] == "cancelled":
                return True
            ap["status"] = "cancelled"
            return True

    def reschedule_appointment(self, appointment_id: str, new_date: str, new_start_time: str) -> Dict[str, Any]:
        target_ap = self._find_appointment(appointment_id)
        _require_date(new_date, "new_date")
        _require_time(new_start_time, "new_start")

        if target_ap["status"] == "cancelled":
            raise ValueError(f"Appointment {appointment_id} is cancelled and cannot be rescheduled.")

        with self._lock:
            # Free the appointment's own slot temporarily so rescheduling
            # onto an overlapping/same slot doesn't collide with itself.
            old_status = target_ap["status"]
            target_ap["status"] = "rescheduling_temp"

            try:
                slots = self.search_slots(target_ap["doctor_id"], new_date)
                if new_start_time not in slots:
                    raise ValueError(f"Slot {new_start_time} on {new_date} is not available.")

                start_dt = datetime.strptime(f"{new_date} {new_start_time}", "%Y-%m-%d %H:%M")
                end_dt = start_dt + timedelta(minutes=self.data["clinic"]["slot_minutes"])

                target_ap["date"] = new_date
                target_ap["start"] = new_start_time
                target_ap["end"] = end_dt.strftime("%H:%M")
                target_ap["status"] = "booked"
                return target_ap
            except Exception:
                target_ap["status"] = old_status
                raise
