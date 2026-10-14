import { computed } from '@angular/core';
import { patchState, signalStore, withComputed, withHooks, withMethods, withState } from '@ngrx/signals';
import { CatalogProduct } from '../products/product-catalog.store';

const CART_STORAGE_KEY = 'bazarstore.pending-cart';

export interface CartItem {
    product: CatalogProduct;
    quantity: number;
}

interface CartState {
    items: CartItem[];
}

const initialState: CartState = { items: [] };

function readPersistedCart(): CartItem[] {
    try {
        const saved = sessionStorage.getItem(CART_STORAGE_KEY);
        if (!saved) return [];
        const parsed = JSON.parse(saved) as CartItem[];
        return Array.isArray(parsed)
            ? parsed.filter((item) => item?.product?.id && Number.isInteger(item.quantity) && item.quantity > 0)
            : [];
    } catch {
        return [];
    }
}

/** Panier partagé par l'accueil et le catalogue, conservé dans la session du navigateur. */
export const CartStore = signalStore(
    { providedIn: 'root' },
    withState(initialState),
    withComputed(({ items }) => ({
        // Nombre de produits distincts, pas la somme des quantités.
        count: computed(() => items().length),
        total: computed(() => items().reduce((total, item) => total + (item.product.price ?? 0) * item.quantity, 0))
    })),
    withMethods((store) => {
        // Renvoie false si le stockage est indisponible ; le panier en mémoire reste utilisable.
        const update = (items: CartItem[]): boolean => {
            patchState(store, { items });
            try {
                if (items.length) sessionStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
                else sessionStorage.removeItem(CART_STORAGE_KEY);
                return true;
            } catch {
                return false;
            }
        };

        return {
            add(product: CatalogProduct): boolean {
                const items = store.items();
                return update(items.some((item) => item.product.id === product.id)
                    ? items.map((item) => item.product.id === product.id ? { ...item, quantity: item.quantity + 1 } : item)
                    : [...items, { product, quantity: 1 }]);
            },
            changeQuantity(index: number, change: number): boolean {
                const items = store.items();
                const item = items[index];
                if (!item) return true;
                const quantity = item.quantity + change;
                return update(quantity > 0
                    ? items.map((entry, itemIndex) => itemIndex === index ? { ...entry, quantity } : entry)
                    : items.filter((_, itemIndex) => itemIndex !== index));
            },
            remove(index: number): boolean {
                return update(store.items().filter((_, itemIndex) => itemIndex !== index));
            },
            clear(): void {
                update([]);
            },
            persist(): boolean {
                return update(store.items());
            }
        };
    }),
    withHooks({
        onInit(store) {
            patchState(store, { items: readPersistedCart() });
        }
    })
);
