import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, finalize, of, shareReplay, tap, throwError } from 'rxjs';
import { AuthService } from '../auth/auth.service';

const USERS_API = '/api/v1/users';

export interface ManagedUser {
    id: string;
    name: string;
    email: string;
    role: string;
    is_active: boolean;
    agent_id: string | null;
    created_at: string;
}

export interface CreateManagedUser {
    name: string;
    email: string;
    password: string;
    role: string;
}

export interface UpdateManagedUser {
    name?: string;
    email?: string;
    role?: string;
    is_active?: boolean;
    password?: string;
}

interface UserAdminState {
    users: ManagedUser[];
    loaded: boolean;
    loading: boolean;
    ownerId: string | null;
}

const initialState: UserAdminState = {
    users: [],
    loaded: false,
    loading: false,
    ownerId: null
};

export const UserAdminStore = signalStore(
    { providedIn: 'root' },
    withState(initialState),
    withMethods((store) => {
        const http = inject(HttpClient);
        const auth = inject(AuthService);
        let listRequest: Observable<ManagedUser[]> | null = null;

        return {
            list(): Observable<ManagedUser[]> {
                const currentUserId = auth.currentUser()?.id ?? null;
                if (store.loaded() && store.ownerId() !== currentUserId) {
                    patchState(store, { users: [], loaded: false, ownerId: null });
                }
                if (store.loaded()) return of(store.users());
                if (listRequest) return listRequest;

                patchState(store, { loading: true });
                listRequest = http.get<ManagedUser[]>(USERS_API).pipe(
                    tap((users) => patchState(store, { users, loaded: true, ownerId: currentUserId })),
                    catchError((error: unknown) => throwError(() => error)),
                    finalize(() => {
                        listRequest = null;
                        patchState(store, { loading: false });
                    }),
                    shareReplay({ bufferSize: 1, refCount: false })
                );
                return listRequest;
            },

            create(user: CreateManagedUser): Observable<ManagedUser> {
                return http.post<ManagedUser>(USERS_API, user).pipe(
                    tap((created) => {
                        if (store.loaded()) patchState(store, { users: [created, ...store.users()] });
                    })
                );
            },

            update(id: string, changes: UpdateManagedUser): Observable<ManagedUser> {
                return http.patch<ManagedUser>(`${USERS_API}/${encodeURIComponent(id)}`, changes).pipe(
                    tap((updated) => {
                        if (store.loaded()) patchState(store, { users: store.users().map((user) => user.id === updated.id ? updated : user) });
                    })
                );
            },

            delete(id: string): Observable<void> {
                return http.delete<void>(`${USERS_API}/${encodeURIComponent(id)}`).pipe(
                    tap(() => {
                        if (store.loaded()) patchState(store, { users: store.users().filter((user) => user.id !== id) });
                    })
                );
            }
        };
    })
);
