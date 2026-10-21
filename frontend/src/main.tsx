import React from "react";
import ReactDOM from "react-dom/client";

import AuthRoot from "./AuthRoot";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AuthRoot />
  </React.StrictMode>,
);
