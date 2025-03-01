export class JunjoGraphError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'JunjoGraphError'
  }
}
