/**
 * Ordre aléatoire stable : chaque élément reçoit un rang tiré une seule fois,
 * donc la liste est mélangée à chaque instance mais ne bouge plus ensuite
 * (indispensable entre deux rendus ou deux lots de défilement infini).
 */
export class RandomOrder {
    private readonly ranks = new Map<string, number>();

    sort<T extends { id: string }>(items: T[]): T[] {
        return [...items].sort((a, b) => this.rank(a.id) - this.rank(b.id));
    }

    private rank(id: string): number {
        let rank = this.ranks.get(id);
        if (rank === undefined) {
            rank = Math.random();
            this.ranks.set(id, rank);
        }
        return rank;
    }
}
