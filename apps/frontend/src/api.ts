export type Member = { id: string; email: string; role: string };
export type Identity = Member & {
  family: { id: string; name: string };
  csrf_token: string;
};
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: `Request failed (${response.status})` }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Please check your input.",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
