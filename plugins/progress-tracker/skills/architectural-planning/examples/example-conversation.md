# Architectural Planning — Examples and Guidance

## Example Conversation

**User**: `/prog plan Build a real-time chat application`

**Skill Response**:

1. **Analyze**: Real-time chat needs WebSocket, message persistence, online status
2. **Question**: Expected concurrent users?
3. **Recommend**:
   - Small scale (<1000): Node.js + Socket.io + Redis
   - Large scale (>10000): Go + WebSocket + Redis Cluster + RabbitMQ
4. **Document**: Save decisions to `docs/progress-tracker/architecture/architecture.md`
5. **Guide**: Suggest running `/prog init` next

## Questions to Ask

When planning architecture, clarify:
- **Scale**: Concurrent users, data volume, growth rate
- **Reliability**: Uptime requirements, fault tolerance needs
- **Performance**: Latency requirements, throughput targets
- **Security**: Authentication needs, data sensitivity
- **Team**: Size, expertise, development timeline
- **Constraints**: Budget, existing systems, regulatory requirements
