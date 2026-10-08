import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { EMPTY, catchError, from, map, of, switchMap } from 'rxjs';

const GOOGLE_SCRIPT_URL = 'https://accounts.google.com/gsi/client';

interface GoogleRuntimeConfig {
    googleClientId?: string;
}

interface GoogleNonceResponse {
    nonce: string;
}

interface GoogleCredentialResponse {
    credential?: string;
}

interface GoogleIdentityApi {
    initialize(options: {
        client_id: string;
        nonce: string;
        callback: (response: GoogleCredentialResponse) => void;
    }): void;
    renderButton(
        parent: HTMLElement,
        options: {
            theme: 'outline';
            size: 'large';
            text: 'continue_with';
            shape: 'rectangular';
            logo_alignment: 'left';
            width: number;
        }
    ): void;
}

declare global {
    interface Window {
        google?: {
            accounts: {
                id: GoogleIdentityApi;
            };
        };
    }
}

@Injectable({ providedIn: 'root' })
export class GoogleIdentityService {
    private readonly http = inject(HttpClient);
    private nonceRefreshTimer?: number;
    private nonceRequestInFlight = false;
    private visibilityRefresh?: () => void;

    renderButton(
        host: HTMLElement,
        onCredential: (credential: string) => void,
        onError: (message: string) => void,
        onReady: () => void
    ): void {
        this.http
            .get<GoogleRuntimeConfig>('/runtime-config.json')
            .pipe(
                switchMap((config) => {
                    return this.http
                        .get<GoogleRuntimeConfig>('/runtime-config.local.json')
                        .pipe(
                            catchError(() => of({} as GoogleRuntimeConfig)),
                            map((localConfig) => localConfig.googleClientId?.trim() || config.googleClientId?.trim()),
                            switchMap((clientId) => {
                                if (!clientId) {
                                    onError('La connexion Google nécessite un identifiant client configuré.');
                                    return EMPTY;
                                }

                                return from(this.loadGoogleScript()).pipe(map(() => clientId));
                            })
                        );
                })
            )
            .subscribe({
                next: (clientId) => {
                    const googleIdentity = window.google?.accounts.id;
                    if (!googleIdentity) {
                        onError('Le service Google Identity n’a pas pu être chargé.');
                        return;
                    }

                    const initializeButton = (nonce: string) => {
                        googleIdentity.initialize({
                            client_id: clientId,
                            nonce,
                            callback: (response) => {
                                if (!response.credential) {
                                    onError('Google n’a pas renvoyé de justificatif de connexion.');
                                    return;
                                }
                                onCredential(response.credential);
                            }
                        });
                        host.replaceChildren();
                        googleIdentity.renderButton(host, {
                            theme: 'outline',
                            size: 'large',
                            text: 'continue_with',
                            shape: 'rectangular',
                            logo_alignment: 'left',
                            width: Math.round(host.getBoundingClientRect().width) || 360
                        });
                    };

                    const refreshNonce = (initial = false) => {
                        if (this.nonceRequestInFlight || !host.isConnected) return;
                        this.nonceRequestInFlight = true;
                        this.http
                            .get<GoogleNonceResponse>('/api/v1/auth/google/nonce', { withCredentials: true })
                            .subscribe({
                                next: ({ nonce }) => {
                                    this.nonceRequestInFlight = false;
                                    initializeButton(nonce);
                                    if (initial) onReady();
                                },
                                error: () => {
                                    this.nonceRequestInFlight = false;
                                    if (initial) onError('La configuration ou le service Google est indisponible.');
                                }
                            });
                    };

                    // Le nonce expire au bout de 5 minutes côté API. Renouveler
                    // avant son expiration évite qu’un onglet laissé ouvert
                    // affiche un bouton Google utilisant un nonce périmé.
                    if (this.nonceRefreshTimer !== undefined) {
                        window.clearInterval(this.nonceRefreshTimer);
                    }
                    if (this.visibilityRefresh) {
                        document.removeEventListener('visibilitychange', this.visibilityRefresh);
                    }
                    refreshNonce(true);
                    this.nonceRefreshTimer = window.setInterval(() => refreshNonce(), 4 * 60 * 1000);
                    this.visibilityRefresh = () => {
                        if (document.visibilityState === 'visible') refreshNonce();
                    };
                    document.addEventListener('visibilitychange', this.visibilityRefresh);
                },
                error: () => onError('La configuration ou le service Google est indisponible.')
            });
    }

    private loadGoogleScript(): Promise<void> {
        if (window.google?.accounts.id) {
            return Promise.resolve();
        }

        return new Promise<void>((resolve, reject) => {
            const script = document.createElement('script');
            script.src = GOOGLE_SCRIPT_URL;
            script.async = true;
            script.defer = true;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error('Google Identity script failed to load.'));
            document.head.append(script);
        });
    }
}
