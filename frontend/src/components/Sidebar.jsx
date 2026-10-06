import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Circle, Disc } from 'lucide-react'; // Placeholder icons for the circles shown in the design

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  const isQueue = location.pathname === '/';
  
  return (
    <div className="sidebar">
      <div 
        className={`sidebar-icon ${isQueue ? 'active' : ''}`}
        onClick={() => navigate('/')}
      >
        <Circle size={16} />
      </div>
      <div className="sidebar-icon">
        <Circle size={16} />
      </div>
      <div className="sidebar-icon">
        <Circle size={16} />
      </div>
      <div className="sidebar-icon">
        <Circle size={16} />
      </div>
      <div className="sidebar-icon">
        <Circle size={16} />
      </div>
      <div className="sidebar-icon">
        <Circle size={16} />
      </div>
    </div>
  );
}
