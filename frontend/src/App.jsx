import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import HandoffQueue from './components/HandoffQueue';
import ConversationDetail from './components/ConversationDetail';

function App() {
  return (
    <>
      <Sidebar />
      <Routes>
        <Route path="/" element={<HandoffQueue />} />
        <Route path="/conversation/:id" element={<ConversationDetail />} />
      </Routes>
    </>
  );
}

export default App;
