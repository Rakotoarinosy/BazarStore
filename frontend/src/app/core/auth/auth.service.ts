import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, map, shareReplay, tap } from 'rxjs';

const AUTH_API = '/api/v1/auth';

export interface AuthProfile {
    id: string;
    email: string;
    name: string;
    role: string;
    agent_id: string | null;
    created_at: string;
}

export interface AuthSession {
    access_token: string;
    token_type: 'bearer';
    expires_in: number;
    user: AuthProfile;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
    private readonly http = inject(HttpClient);
    private refreshRequest: Observable<AuthSession> | null = null;

    private readonly accessTokenState = signal<string | null>(null);
    readonly accessToken = this.accessTokenState.asReadonly();
    readonly currentUser = signal<AuthProfile | null>(null);

    login(email: string, password: string): Observable<AuthSession> {
        return this.http
            .post<AuthSession>(`${AUTH_API}/login`, { email, password }, { withCredentials: true })
            .pipe(tap((session) => this.storeSession(session)));
    }

    loginWithGoogle(credential: string): Observable<AuthSession> {
        return this.http
            .post<AuthSession>(`${AUTH_API}/google`, { credential }, { withCredentials: true })
            .pipe(tap((session) => this.storeSession(session)));
    }

    register(name: string, email: string, password: string): Observable<AuthProfile> {
        return this.http.post<AuthProfile>(`${AUTH_API}/register`, { name, email, password });
    }

    refresh(): Observable<string> {
        if (!this.refreshRequest) {
            this.refreshRequest = this.http
                .post<AuthSession>(`${AUTH_API}/refresh`, {}, { withCredentials: true })
                .pipe(
                    tap((session) => this.storeSession(session)),
                    finalize(() => (this.refreshRequest = null)),
                    shareReplay({ bufferSize: 1, refCount: false })
                );
        }

        return this.refreshRequest.pipe(map((session) => session.access_token));
    }

    logout(): Observable<void> {
        return this.http.post<void>(`${AUTH_API}/logout`, {}, { withCredentials: true }).pipe(
            finalize(() => this.clearSession())
        );
    }

    clearSession(): void {
        this.accessTokenState.set(null);
        this.currentUser.set(null);
    }

    private storeSession(session: AuthSession): void {
        this.accessTokenState.set(session.access_token);
        this.currentUser.set(session.user);
    }
}

export function authErrorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
        return 'Une erreur inattendue est survenue. Veuillez réessayer.';
    }

    if (error.status === 0) {
        return 'Le serveur BazarStore est injoignable. Vérifiez que le backend est démarré.';
    }

    if (error.status === 401) {
        return 'Adresse e-mail ou mot de passe incorrect.';
    }

    if (error.status === 409) {
        return 'Un compte existe déjà avec cette adresse e-mail.';
    }

    if (error.status === 422) {
        return 'Vérifiez les informations saisies et la politique de mot de passe.';
    }

    if (error.status === 429) {
        return 'Trop de tentatives. Veuillez patienter avant de réessayer.';
    }

    if (error.status === 503) {
        return 'La connexion demandée n’est pas configurée ou est temporairement indisponible.';
    }

    return 'Le service d’authentification a rencontré un problème. Veuillez réessayer plus tard.';
}

export function googleAuthErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse && error.status === 401) {
        return 'Google a refusé la connexion. Rechargez la page et réessayez.';
    }

    return authErrorMessage(error);
}
