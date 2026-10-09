import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { EMPTY, distinctUntilChanged, map, switchMap } from 'rxjs';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { AppMenuitem } from './app.menuitem';
import { AuthService } from '@/app/core/auth/auth.service';
import { OrderAdminStore } from '@/app/core/orders/order-admin.store';

const STAFF_ROLES = ['admin', 'commercial', 'manager'];

@Component({
    selector: 'app-menu',
    standalone: true,
    imports: [CommonModule, AppMenuitem, RouterModule],
    templateUrl: './app.menu.html',
})
export class AppMenu {
    private readonly auth = inject(AuthService);
    private readonly orders = inject(OrderAdminStore);
    private readonly destroyRef = inject(DestroyRef);

    model: MenuItem[] = [];

    constructor() {
        // Temps réel des commandes (badge + tableau), réservé à l'équipe : démarre dès que
        // la session est chargée, s'arrête à la déconnexion ou quand on quitte le backoffice.
        toObservable(this.auth.currentUser)
            .pipe(
                map((user) => STAFF_ROLES.includes(user?.role ?? '')),
                distinctUntilChanged(),
                switchMap((isStaff) => (isStaff ? this.orders.watch() : EMPTY)),
                takeUntilDestroyed(this.destroyRef)
            )
            .subscribe();
    }

    ngOnInit() {
        this.model = [
            {
                label: 'Backoffice',
                items: [
                    { label: 'Dashboard', icon: 'pi pi-fw pi-home', routerLink: ['/backoffice/dashboard'] },
                    { label: 'Images boutique', icon: 'pi pi-fw pi-images', routerLink: ['/backoffice/storefront-media'] },
                    { label: 'Utilisateurs', icon: 'pi pi-fw pi-users', routerLink: ['/backoffice/users'] },
                    { label: 'Catégories', icon: 'pi pi-fw pi-tags', routerLink: ['/backoffice/categories'] },
                    { label: 'Produits', icon: 'pi pi-fw pi-box', routerLink: ['/backoffice/products'] },
                    { label: 'Commandes', icon: 'pi pi-fw pi-shopping-cart', routerLink: ['/backoffice/orders'], badgeCount: this.orders.openCount, badgeTitle: 'commande(s) pas encore livrée(s)' }
                ]
            },
            {
                label: 'Boutique',
                items: [{ label: 'Voir la boutique', icon: 'pi pi-fw pi-shop', routerLink: ['/'] }]
            }
        ];
    }
}
