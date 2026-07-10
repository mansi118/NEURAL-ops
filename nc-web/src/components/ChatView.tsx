import { useEffect, useRef, useState } from "react";
import type { MatrixService } from "../lib/matrixService";
import type { ChatMessage, RoomSummary } from "../lib/matrixService";
import { mergeMessages, addOptimistic } from "../lib/timeline";
import { optimisticMessage } from "../lib/messages";

// Core chat surface (PR-B): room list, live timeline with NEop-aware rendering, composer with
// optimistic echo. All ordering/parsing lives in the tested pure modules; this is the thin view.
export default function ChatView({ svc }: { svc: MatrixService }) {
  const rooms = svc.rooms();
  const [activeRoom, setActiveRoom] = useState<string | null>(rooms[0]?.roomId ?? null);

  return (
    <div className="nc-chat">
      <aside className="nc-sidebar">
        <RoomList rooms={rooms} active={activeRoom} onSelect={setActiveRoom} />
      </aside>
      <section className="nc-main">
        {activeRoom ? (
          <Room svc={svc} roomId={activeRoom} />
        ) : (
          <p className="nc-empty">No rooms yet.</p>
        )}
      </section>
    </div>
  );
}

function RoomList({
  rooms,
  active,
  onSelect,
}: {
  rooms: RoomSummary[];
  active: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="nc-rooms">
      {rooms.map((r) => (
        <li key={r.roomId}>
          <button
            className={r.roomId === active ? "nc-room active" : "nc-room"}
            onClick={() => onSelect(r.roomId)}
          >
            {r.name || r.roomId}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Room({ svc, roomId }: { svc: MatrixService; roomId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const localCounter = useRef(0);

  useEffect(() => {
    setMessages(svc.roomMessages(roomId));
    const unsub = svc.subscribeMessages((rid, msg) => {
      if (rid === roomId) setMessages((m) => mergeMessages(m, [msg]));
    });
    return unsub;
  }, [svc, roomId]);

  async function onSend(body: string) {
    const self = svc.currentUserId() ?? "@me";
    const localId = `~local-${++localCounter.current}`;
    setMessages((m) => addOptimistic(m, optimisticMessage(localId, self, body, Date.now())));
    try {
      const realId = await svc.send(roomId, body);
      // promote the pending twin to the real id so the incoming echo dedups against it
      setMessages((m) =>
        m.map((x) => (x.eventId === localId ? { ...x, eventId: realId, pending: false } : x)),
      );
    } catch {
      setMessages((m) => m.filter((x) => x.eventId !== localId));
    }
  }

  return (
    <>
      <Timeline messages={messages} />
      <Composer onSend={onSend} />
    </>
  );
}

function Timeline({ messages }: { messages: ChatMessage[] }) {
  return (
    <ol className="nc-timeline">
      {messages.map((m) => (
        <li
          key={m.eventId}
          className={
            "nc-msg" + (m.isNeop ? " neop" : "") + (m.isSelf ? " self" : "") + (m.pending ? " pending" : "")
          }
        >
          <span className="nc-sender">{m.displayName}</span>
          <span className="nc-body">{m.body}</span>
        </li>
      ))}
    </ol>
  );
}

function Composer({ onSend }: { onSend: (body: string) => void | Promise<void> }) {
  const [text, setText] = useState("");
  function submit(e: React.FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    setText("");
    void onSend(body);
  }
  return (
    <form className="nc-composer" onSubmit={submit}>
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Message…" />
      <button type="submit" disabled={!text.trim()}>
        Send
      </button>
    </form>
  );
}
