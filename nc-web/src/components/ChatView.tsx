import { useEffect, useMemo, useRef, useState } from "react";
import type { MatrixService } from "../lib/matrixService";
import type { ChatMessage, RoomSummary } from "../lib/matrixService";
import { mergeMessages, addOptimistic } from "../lib/timeline";
import { optimisticMessage } from "../lib/messages";
import { initials, colorFor } from "../lib/avatar";
import { formatTs } from "../lib/time";
import { humanizeSendError } from "../lib/errors";

// Core chat surface with a usability layer (Design of Everyday Things): visible feedback while a NEop
// is processing, recoverable send errors, seat-named affordances. Ordering/parsing stay in tested modules.
export default function ChatView({ svc }: { svc: MatrixService }) {
  const rooms = svc.rooms();
  const [activeRoom, setActiveRoom] = useState<string | null>(rooms[0]?.roomId ?? null);
  const activeName = rooms.find((r) => r.roomId === activeRoom)?.name ?? "";

  return (
    <div className="nc-chat">
      <aside className="nc-sidebar">
        <RoomList rooms={rooms} active={activeRoom} onSelect={setActiveRoom} />
      </aside>
      <section className="nc-main">
        {activeRoom ? (
          <Room svc={svc} roomId={activeRoom} roomName={activeName} />
        ) : (
          <p className="nc-empty">
            No conversations yet. When you're added to a room with a NEop, it appears here.
          </p>
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
    <ul className="nc-rooms" aria-label="Conversations">
      {rooms.map((r) => (
        <li key={r.roomId}>
          <button
            className={r.roomId === active ? "nc-room active" : "nc-room"}
            aria-current={r.roomId === active}
            onClick={() => onSelect(r.roomId)}
          >
            {r.name || r.roomId}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Room({ svc, roomId, roomName }: { svc: MatrixService; roomId: string; roomName: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [awaiting, setAwaiting] = useState(false); // a NEop reply is expected (feedback: "thinking…")
  const [sendError, setSendError] = useState<string | null>(null);
  const localCounter = useRef(0);
  const awaitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // the NEop currently in the room (from the newest NEop message) — names the "thinking" indicator
  const neopName = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].isNeop) return messages[i].displayName;
    return null;
  }, [messages]);

  useEffect(() => {
    setAwaiting(false);
    setSendError(null);
    setMessages(svc.roomMessages(roomId));
    const unsub = svc.subscribeMessages((rid, msg) => {
      if (rid !== roomId) return;
      setMessages((m) => mergeMessages(m, [msg]));
      if (msg.isNeop) {
        setAwaiting(false);
        if (awaitTimer.current) clearTimeout(awaitTimer.current);
      }
    });
    return () => {
      unsub();
      if (awaitTimer.current) clearTimeout(awaitTimer.current);
    };
  }, [svc, roomId]);

  // keep the newest message in view (visible system state)
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, awaiting]);

  async function onSend(body: string) {
    const self = svc.currentUserId() ?? "@me";
    const localId = `~local-${++localCounter.current}`;
    setSendError(null);
    setMessages((m) => addOptimistic(m, optimisticMessage(localId, self, body, Date.now())));
    setAwaiting(true);
    if (awaitTimer.current) clearTimeout(awaitTimer.current);
    awaitTimer.current = setTimeout(() => setAwaiting(false), 60000); // safety: don't spin forever
    try {
      const realId = await svc.send(roomId, body);
      setMessages((m) =>
        m.map((x) => (x.eventId === localId ? { ...x, eventId: realId, pending: false } : x)),
      );
    } catch (e) {
      setMessages((m) => m.filter((x) => x.eventId !== localId));
      setAwaiting(false);
      if (awaitTimer.current) clearTimeout(awaitTimer.current);
      setSendError(humanizeSendError(e));
    }
  }

  return (
    <>
      <Timeline messages={messages} awaiting={awaiting} neopName={neopName} endRef={endRef} />
      {sendError && (
        <div className="nc-send-error" role="alert">
          <span>{sendError}</span>
          <button onClick={() => setSendError(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}
      <Composer onSend={onSend} placeholder={placeholderFor(roomName)} />
    </>
  );
}

function placeholderFor(roomName: string): string {
  const n = roomName.trim();
  return n ? `Message ${n}…` : "Message…";
}

function Timeline({
  messages,
  awaiting,
  neopName,
  endRef,
}: {
  messages: ChatMessage[];
  awaiting: boolean;
  neopName: string | null;
  endRef: React.RefObject<HTMLDivElement>;
}) {
  return (
    <ol className="nc-timeline">
      {messages.map((m) => (
        <li
          key={m.eventId}
          className={
            "nc-msg" + (m.isNeop ? " neop" : "") + (m.isSelf ? " self" : "") + (m.pending ? " pending" : "")
          }
        >
          <span className="nc-avatar" style={{ background: colorFor(m.displayName) }} aria-hidden>
            {initials(m.displayName)}
          </span>
          <div className="nc-msg-body">
            <div className="nc-msg-head">
              <span className="nc-sender">{m.displayName}</span>
              {m.isNeop && <span className="nc-badge">NEop</span>}
              <span className="nc-time">{m.pending ? "…" : formatTs(m.ts)}</span>
            </div>
            <span className="nc-body">{m.body}</span>
          </div>
        </li>
      ))}
      {awaiting && (
        <li className="nc-msg neop nc-thinking" aria-live="polite">
          <span className="nc-avatar" style={{ background: colorFor(neopName ?? "neop") }} aria-hidden>
            {initials(neopName ?? "N")}
          </span>
          <div className="nc-msg-body">
            <span className="nc-body nc-dots">
              <i></i><i></i><i></i>
              <span className="nc-vh">{neopName ?? "The assistant"} is thinking</span>
            </span>
          </div>
        </li>
      )}
      <div ref={endRef} />
    </ol>
  );
}

function Composer({
  onSend,
  placeholder,
}: {
  onSend: (body: string) => void | Promise<void>;
  placeholder: string;
}) {
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
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        aria-label="Message"
        autoFocus
      />
      <button type="submit" disabled={!text.trim()} aria-label="Send message">
        Send
      </button>
    </form>
  );
}
