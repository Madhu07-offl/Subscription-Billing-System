// One error type for both the mock and the real client, so pages catch the same thing.
// `details` is [{ field, message }] (contract/API.md section 4).
export class ApiError extends Error {
  constructor(code, message, details = []) {
    super(message);
    this.code = code;
    this.details = details;
  }
}
