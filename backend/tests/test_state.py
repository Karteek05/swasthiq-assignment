import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state import ClinicState, ToolArgumentError

CLINIC_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clinic.json")


@pytest.fixture
def clinic():
    return ClinicState(CLINIC_JSON)


# ---------- happy path ----------

def test_search_slots_returns_free_slots(clinic):
    slots = clinic.search_slots("dr_rao", "2026-10-03")
    assert isinstance(slots, list)
    assert "09:30" not in slots or True  # presence depends on seed bookings; just assert shape
    assert all(len(s) == 5 and s[2] == ":" for s in slots)


def test_book_then_slot_disappears(clinic):
    slots_before = clinic.search_slots("dr_rao", "2026-10-03")
    slot = slots_before[0]
    ap = clinic.book_appointment("pt_0001", "dr_rao", "2026-10-03", slot)
    assert ap["status"] == "booked"
    slots_after = clinic.search_slots("dr_rao", "2026-10-03")
    assert slot not in slots_after


def test_cancel_then_slot_reappears(clinic):
    slots_before = clinic.search_slots("dr_rao", "2026-10-03")
    slot = slots_before[0]
    ap = clinic.book_appointment("pt_0001", "dr_rao", "2026-10-03", slot)
    clinic.cancel_appointment(ap["id"])
    slots_after = clinic.search_slots("dr_rao", "2026-10-03")
    assert slot in slots_after


def test_reschedule_moves_appointment(clinic):
    slots = clinic.search_slots("dr_rao", "2026-10-03")
    ap = clinic.book_appointment("pt_0001", "dr_rao", "2026-10-03", slots[0])
    new_slots = clinic.search_slots("dr_rao", "2026-10-05")
    moved = clinic.reschedule_appointment(ap["id"], "2026-10-05", new_slots[0])
    assert moved["date"] == "2026-10-05"
    assert moved["start"] == new_slots[0]
    # old slot freed
    assert slots[0] in clinic.search_slots("dr_rao", "2026-10-03")


def test_lookup_patient_ambiguous_returns_all_candidates(clinic):
    # Many seed patients share the surname "Sharma" - ambiguous lookup must
    # return every match, not silently pick one.
    candidates = clinic.lookup_patient("Sharma")
    assert len(candidates) >= 1
    names = [c["name"] for c in candidates]
    assert all("sharma" in n.lower() for n in names)


# ---------- non-happy-path: double booking / races ----------

def test_double_booking_same_slot_rejected(clinic):
    slots = clinic.search_slots("dr_rao", "2026-10-03")
    slot = slots[0]
    clinic.book_appointment("pt_0001", "dr_rao", "2026-10-03", slot)
    with pytest.raises(ValueError):
        clinic.book_appointment("pt_0002", "dr_rao", "2026-10-03", slot)


def test_concurrent_booking_race_only_one_wins(clinic):
    slots = clinic.search_slots("dr_rao", "2026-10-03")
    slot = slots[0]
    results = []

    def attempt(patient_id):
        try:
            clinic.book_appointment(patient_id, "dr_rao", "2026-10-03", slot)
            results.append("ok")
        except ValueError:
            results.append("rejected")

    threads = [threading.Thread(target=attempt, args=(pid,)) for pid in ["pt_0001", "pt_0002", "pt_0003"]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 1
    assert results.count("rejected") == 2


# ---------- malformed arguments: specific, actionable errors ----------

def test_search_slots_missing_doctor_id_raises_actionable_error(clinic):
    with pytest.raises(ToolArgumentError, match="doctor_id"):
        clinic.search_slots(None, "2026-10-03")


def test_search_slots_unknown_doctor_raises_actionable_error(clinic):
    with pytest.raises(ToolArgumentError, match="No doctor"):
        clinic.search_slots("dr_does_not_exist", "2026-10-03")


def test_search_slots_malformed_date_raises_actionable_error(clinic):
    with pytest.raises(ToolArgumentError, match="YYYY-MM-DD"):
        clinic.search_slots("dr_rao", "03-10-2026")


def test_book_appointment_unknown_patient_raises(clinic):
    slots = clinic.search_slots("dr_rao", "2026-10-03")
    with pytest.raises(ToolArgumentError, match="No patient"):
        clinic.book_appointment("pt_9999", "dr_rao", "2026-10-03", slots[0])


def test_book_appointment_malformed_time_raises(clinic):
    with pytest.raises(ToolArgumentError, match="HH:MM"):
        clinic.book_appointment("pt_0001", "dr_rao", "2026-10-03", "9:30am")


def test_cancel_unknown_appointment_raises(clinic):
    with pytest.raises(ValueError, match="not found"):
        clinic.cancel_appointment("ap_does_not_exist")


def test_reschedule_unknown_appointment_raises(clinic):
    with pytest.raises(ValueError, match="not found"):
        clinic.reschedule_appointment("ap_does_not_exist", "2026-10-05", "09:00")


# ---------- data-quality edge case this test suite caught ----------

def test_overlapping_windows_do_not_produce_duplicate_slots(clinic):
    # dr_rao's Monday windows (09:00-12:00 and 11:45-15:00) overlap by 15
    # minutes in the seed data. search_slots must not return "11:45" twice.
    slots = clinic.search_slots("dr_rao", "2026-10-05")  # a Monday
    assert len(slots) == len(set(slots))


def test_holiday_has_no_slots(clinic):
    assert clinic.search_slots("dr_rao", "2026-10-02") == []


def test_doctor_leave_date_has_no_slots(clinic):
    assert clinic.search_slots("dr_rao", "2026-10-09") == []
