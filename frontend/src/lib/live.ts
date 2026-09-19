import { WS_URL } from "@/lib/config";
import { useKea } from "@/lib/store";
import type { WsMessage } from "@/lib/types";

/** Live WebSocket client: snapshot first (server sends it on connect), reconnect with backoff. */
export function connectLive(): () => void {
  let socket: WebSocket | null = null;
  let attempt = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let queue: WsMessage[] = [];
  let frame = 0;

  // batch state updates per animation frame
  const flush = () => {
    frame = 0;
    const batch = queue;
    queue = [];
    for (const m of batch) useKea.getState().applyMessage(m);
  };

  const open = () => {
    useKea.getState().setEnv({ conn: attempt === 0 ? "connecting" : "reconnecting" });
    socket = new WebSocket(WS_URL);
    socket.onopen = () => {
      attempt = 0;
      useKea.getState().setEnv({ conn: "connected" });
    };
    socket.onmessage = (ev) => {
      queue.push(JSON.parse(ev.data as string) as WsMessage);
      if (!frame) frame = requestAnimationFrame(flush);
    };
    socket.onclose = () => {
      if (stopped) return;
      useKea.getState().setEnv({ conn: "reconnecting" });
      const base = Math.min(10_000, 500 * 2 ** attempt++);
      timer = setTimeout(open, base * (0.5 + Math.random() * 0.5)); // exponential backoff with jitter
    };
  };
  open();

  return () => {
    stopped = true;
    clearTimeout(timer);
    if (frame) cancelAnimationFrame(frame);
    socket?.close();
  };
}
