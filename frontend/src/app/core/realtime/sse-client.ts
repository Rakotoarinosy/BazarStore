import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { AuthService } from '../auth/auth.service';

export interface ServerSentEvent {
    event: string;
    data: string;
}

/** Reconnexion après une erreur : 2 s, 4 s, 8 s… plafonné à 30 s. */
const MAX_RETRY_MS = 30_000;

/**
 * Client Server-Sent Events authentifié.
 *
 * `fetch` plutôt qu'EventSource : EventSource ne peut pas envoyer le jeton Bearer.
 * Reconnexion automatique : le serveur ferme volontairement le flux toutes les 2 min,
 * et le jeton d'accès est renouvelé s'il a expiré entre-temps.
 */
@Injectable({ providedIn: 'root' })
export class SseClient {
    private readonly auth = inject(AuthService);

    stream(url: string): Observable<ServerSentEvent> {
        return new Observable<ServerSentEvent>((subscriber) => {
            let controller: AbortController | null = null;
            let retryTimer: ReturnType<typeof setTimeout> | undefined;
            let stopped = false;
            let failures = 0;

            const schedule = (delay: number) => {
                if (!stopped) retryTimer = setTimeout(() => void connect(), delay);
            };

            const connect = async (tokenRefreshed = false): Promise<void> => {
                controller = new AbortController();
                try {
                    const token = this.auth.accessToken();
                    const response = await fetch(url, {
                        headers: { Accept: 'text/event-stream', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
                        credentials: 'include',
                        signal: controller.signal
                    });
                    if (response.status === 401 && !tokenRefreshed) {
                        await firstValueFrom(this.auth.refresh());
                        return connect(true);
                    }
                    if (response.status === 401 || response.status === 403) return; // pas autorisé : on n'insiste pas
                    if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);

                    failures = 0;
                    await readServerSentEvents(response.body, (event) => subscriber.next(event));
                    schedule(500); // fin normale du flux : reconnexion immédiate
                } catch {
                    if (stopped) return;
                    failures += 1;
                    schedule(Math.min(MAX_RETRY_MS, 1000 * 2 ** failures));
                }
            };

            void connect();
            return () => {
                stopped = true;
                clearTimeout(retryTimer);
                controller?.abort();
            };
        });
    }
}

/** Lit un flux `text/event-stream` et appelle `onEvent` pour chaque événement complet. */
async function readServerSentEvents(body: ReadableStream<Uint8Array>, onEvent: (event: ServerSentEvent) => void): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
        const { value, done } = await reader.read();
        if (done) return;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        let separator: number;
        while ((separator = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, separator);
            buffer = buffer.slice(separator + 2);
            let event = 'message';
            const data: string[] = [];
            for (const line of block.split('\n')) {
                if (line.startsWith('event:')) event = line.slice(6).trim();
                else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
                // Les lignes « : ping » (commentaires) et « retry: » sont ignorées.
            }
            if (data.length) onEvent({ event, data: data.join('\n') });
        }
    }
}
