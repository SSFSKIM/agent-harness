import { SwarmError } from "./types.js";
import type { Message } from "./types.js";

export class MessageBus {
  private inboxes = new Map<string, Message[]>();
  private subscribers = new Map<string, (msg: Message) => void>();
  private known = new Set<string>(["coordinator"]); // coordinator inbox always exists

  subscribe(agent: string, handler: (msg: Message) => void): void {
    this.known.add(agent);
    this.subscribers.set(agent, handler);
  }
  unregister(agent: string): void {
    this.known.delete(agent);
    this.subscribers.delete(agent);
    this.inboxes.delete(agent);
  }

  send(to: string, msg: Message): void {
    if (!this.known.has(to)) throw new SwarmError(`unknown recipient ${to}`);
    const sub = this.subscribers.get(to);
    if (sub) { sub(msg); return; }
    const box = this.inboxes.get(to) ?? [];
    box.push(msg);
    this.inboxes.set(to, box);
  }

  drain(agent: string): Message[] {
    const box = this.inboxes.get(agent) ?? [];
    this.inboxes.set(agent, []);
    return box;
  }
}
