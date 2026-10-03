import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

// StrictMode is intentionally not used: the game owns a WebGL context + camera that must be created once.
createRoot(document.getElementById("root")!).render(<App />);
