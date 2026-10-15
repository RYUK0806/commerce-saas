import { useAuth } from "@clerk/react";
import { useCallback } from "react";
import { api } from "../api";

export function useApi() {
  const { getToken } = useAuth();

  const authedApi = useCallback(
    async <T = unknown>(path: string, options: RequestInit = {}): Promise<T> => {
      const token = await getToken();
      return api<T>(path, { ...options, token });
    },
    [getToken],
  );

  return authedApi;
}
