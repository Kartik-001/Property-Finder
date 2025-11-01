import React, { useState } from "react";
import Chat from "./components/Chat";

export default function App() {
  return (
    <div className="app">
      <header>
        <h1>Project Search Chat</h1>
      </header>
      <main>
        <Chat />
      </main>
    </div>
  );
}
