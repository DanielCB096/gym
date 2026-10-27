import { ApiError } from "./api";

export function describeError(error: unknown): string {
  if (error instanceof ApiError && error.message) {
    return error.message;
  }
  return "Ocurrió un error inesperado. Intenta de nuevo.";
}
