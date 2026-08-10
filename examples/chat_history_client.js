// Replace the browser-owned conversationHistory array with this API client.
class ChatHistoryClient {
  constructor() {
    this.activeConversationId = null;
  }

  async request(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `Request failed (${response.status})`);
    }
    return response.status === 204 ? null : response.json();
  }

  list() {
    return this.request("/api/conversations");
  }

  async create(title = "New conversation") {
    const conversation = await this.request("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    this.activeConversationId = conversation.conversationId;
    return conversation;
  }

  async open(conversationId) {
    const conversation = await this.request(
      `/api/conversations/${conversationId}`,
    );
    this.activeConversationId = conversation.conversationId;
    return conversation;
  }

  send(content) {
    if (!this.activeConversationId) {
      throw new Error("Create or open a conversation before sending a message.");
    }
    return this.request(
      `/api/conversations/${this.activeConversationId}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
    );
  }

  rate(messageId, helpful, comment = null) {
    return this.request(
      `/api/conversations/${this.activeConversationId}/messages/${messageId}/feedback`,
      { method: "PUT", body: JSON.stringify({ helpful, comment }) },
    );
  }

  async remove() {
    if (!this.activeConversationId) return;
    await this.request(`/api/conversations/${this.activeConversationId}`, {
      method: "DELETE",
    });
    this.activeConversationId = null;
  }
}