"""Insert a small, repeatable showcase catalog with images stored in MinIO."""

from pathlib import Path

from sqlalchemy import func, select

from src.infrastructure.persistence.database import SessionLocal
from src.infrastructure.persistence.models import ProductCategoryModel, ProductModel
from src.infrastructure.storage.minio_product_images import MinioProductImageStorage

IMAGE_ROOT = Path(__file__).resolve().parents[2] / "frontend/public/demo/images/product"

PRODUCTS = [
    ("BAZ-MODE-001", "T-shirt bleu", "T-shirt confortable pour tous les jours.", 116_000, 18, "mode-vetements", "blue-t-shirt.jpg"),
    ("BAZ-MODE-002", "Baskets urbaines", "Baskets légères pour un usage quotidien.", 312_000, 12, "mode-vetements", "sneakers.jpg"),
    ("BAZ-TECH-001", "Casque audio", "Casque audio circum-aural pour écouter vos contenus préférés.", 700_000, 8, "high-tech-electronique", "headphones.jpg"),
    ("BAZ-TECH-002", "Manette sans fil", "Manette ergonomique compatible avec vos appareils de jeu.", 396_000, 14, "high-tech-electronique", "game-controller.jpg"),
    ("BAZ-ACC-001", "Montre Bamboo", "Montre élégante avec bracelet couleur bambou.", 260_000, 24, "accessoires", "bamboo-watch.jpg"),
    ("BAZ-ACC-002", "Pochette marron", "Pochette compacte pour transporter vos essentiels.", 180_000, 10, "accessoires", "brown-purse.jpg"),
    ("BAZ-SPORT-001", "Tapis de yoga", "Tapis confortable pour vos séances de yoga et d'étirement.", 80_000, 15, "sport-bien-etre", "yoga-mat.jpg"),
    ("BAZ-SPORT-002", "Bracelet connecté bleu", "Bracelet connecté léger pour accompagner vos activités.", 316_000, 9, "sport-bien-etre", "blue-band.jpg"),
]

# Complète chaque catégorie jusqu'à 13 produits actifs afin de pouvoir parcourir
# au moins une page supplémentaire dans la vitrine. Les images sont déjà servies
# par le frontend, donc cette donnée de démonstration ne dépend pas de MinIO.
PAGINATION_PRODUCTS = {
    "mode-vetements": [
        ("T-shirt vert", 118_000, 17, "green-t-shirt.jpg"),
        ("T-shirt gris", 124_000, 11, "grey-t-shirt.jpg"),
        ("T-shirt violet", 126_000, 9, "purple-t-shirt.jpg"),
        ("T-shirt turquoise", 121_000, 14, "teal-t-shirt.jpg"),
        ("T-shirt vert clair", 119_000, 8, "light-green-t-shirt.jpg"),
        ("Baskets Street", 328_000, 6, "shoes.jpg"),
        ("Baskets confort", 305_000, 13, "sneakers.jpg"),
        ("T-shirt essentiel bleu", 112_000, 20, "blue-t-shirt.jpg"),
        ("T-shirt essentiel vert", 115_000, 7, "green-t-shirt.jpg"),
        ("T-shirt essentiel gris", 117_000, 10, "grey-t-shirt.jpg"),
        ("Baskets légères", 319_000, 5, "shoes.jpg"),
        ("T-shirt essentiel violet", 122_000, 16, "purple-t-shirt.jpg"),
        ("T-shirt essentiel turquoise", 120_000, 12, "teal-t-shirt.jpg"),
    ],
    "high-tech-electronique": [
        ("Écouteurs sans fil verts", 245_000, 18, "green-earbuds.jpg"),
        ("Écouteurs sans fil jaunes", 239_000, 7, "yellow-earbuds.jpg"),
        ("Mini enceinte portable", 198_000, 12, "mini-speakers.jpg"),
        ("Casque audio confort", 735_000, 4, "headphones.jpg"),
        ("Manette gaming", 410_000, 9, "game-controller.jpg"),
        ("Coque téléphone dorée", 68_000, 25, "gold-phone-case.jpg"),
        ("Coque téléphone illustrée", 74_000, 15, "painted-phone-case.jpg"),
        ("Enceinte compacte", 215_000, 6, "mini-speakers.jpg"),
        ("Écouteurs confort", 229_000, 11, "yellow-earbuds.jpg"),
        ("Casque audio studio", 780_000, 3, "headphones.jpg"),
        ("Manette sans fil pro", 435_000, 8, "game-controller.jpg"),
        ("Coque téléphone élégante", 72_000, 19, "gold-phone-case.jpg"),
        ("Écouteurs nomades", 252_000, 10, "green-earbuds.jpg"),
    ],
    "accessoires": [
        ("Montre classique noire", 275_000, 8, "black-watch.jpg"),
        ("Bracelet chakra", 92_000, 21, "chakra-bracelet.jpg"),
        ("Bracelet violet", 84_000, 6, "purple-band.jpg"),
        ("Bracelet rose", 86_000, 13, "pink-band.jpg"),
        ("Bracelet vert citron", 89_000, 17, "lime-band.jpg"),
        ("Boucles d'oreilles Galaxy", 145_000, 9, "galaxy-earrings.jpg"),
        ("Collier pierre violette", 168_000, 5, "purple-gemstone-necklace.jpg"),
        ("Pochette rose", 155_000, 12, "pink-purse.jpg"),
        ("Montre au bracelet bambou", 268_000, 10, "bamboo-watch.jpg"),
        ("Bracelet connecté coloré", 298_000, 14, "bracelet.jpg"),
        ("Pochette citadine", 162_000, 7, "brown-purse.jpg"),
        ("Bracelet violet élégant", 95_000, 19, "purple-band.jpg"),
        ("Accessoire pierre naturelle", 172_000, 4, "purple-gemstone-necklace.jpg"),
    ],
    "sport-bien-etre": [
        ("Tapis de yoga turquoise", 84_000, 20, "yoga-mat.jpg"),
        ("Kit yoga essentiel", 145_000, 12, "yoga-set.jpg"),
        ("Bracelet connecté rose", 305_000, 8, "pink-band.jpg"),
        ("Bracelet connecté violet", 309_000, 6, "purple-band.jpg"),
        ("Bracelet connecté vert citron", 302_000, 15, "lime-band.jpg"),
        ("Bracelet connecté bleu ciel", 312_000, 11, "blue-band.jpg"),
        ("Tapis confort quotidien", 89_000, 7, "yoga-mat.jpg"),
        ("Ensemble yoga détente", 158_000, 5, "yoga-set.jpg"),
        ("Bracelet activité rose", 288_000, 14, "pink-band.jpg"),
        ("Bracelet activité violet", 294_000, 9, "purple-band.jpg"),
        ("Tapis d'étirement", 78_000, 18, "yoga-mat.jpg"),
        ("Kit bien-être yoga", 172_000, 10, "yoga-set.jpg"),
        ("Bracelet sport vert", 299_000, 4, "lime-band.jpg"),
    ],
    "maison-decoration": [
        ("Enceinte décorative compacte", 205_000, 12, "mini-speakers.jpg"),
        ("Coffret ambiance gaming", 460_000, 6, "gaming-set.jpg"),
        ("Accessoire maison turquoise", 82_000, 14, "yoga-mat.jpg"),
        ("Rangement essentiel", 96_000, 9, "brown-purse.jpg"),
        ("Objet déco naturel", 138_000, 8, "bamboo-watch.jpg"),
        ("Enceinte pour la maison", 225_000, 5, "mini-speakers.jpg"),
        ("Coffret détente", 185_000, 16, "yoga-set.jpg"),
        ("Accessoire maison pastel", 75_000, 20, "painted-phone-case.jpg"),
        ("Boîte de rangement compacte", 105_000, 7, "pink-purse.jpg"),
        ("Décoration esprit naturel", 148_000, 11, "bamboo-watch.jpg"),
        ("Enceinte nomade maison", 218_000, 13, "mini-speakers.jpg"),
        ("Set confort intérieur", 192_000, 4, "yoga-set.jpg"),
        ("Accessoire déco coloré", 89_000, 10, "gold-phone-case.jpg"),
    ],
    "beaute-soins": [
        ("Bandeau de soin bleu", 42_000, 25, "blue-band.jpg"),
        ("Bandeau de soin rose", 44_000, 18, "pink-band.jpg"),
        ("Bandeau de soin violet", 43_000, 9, "purple-band.jpg"),
        ("Trousse beauté rose", 112_000, 12, "pink-purse.jpg"),
        ("Trousse beauté marron", 118_000, 6, "brown-purse.jpg"),
        ("Accessoire soin quotidien", 58_000, 14, "painted-phone-case.jpg"),
        ("Bandeau bien-être vert", 45_000, 7, "lime-band.jpg"),
        ("Pochette soins compacte", 105_000, 16, "pink-purse.jpg"),
        ("Accessoire beauté pastel", 62_000, 11, "purple-band.jpg"),
        ("Trousse essentielle", 98_000, 5, "brown-purse.jpg"),
        ("Bandeau détente rose", 47_000, 20, "pink-band.jpg"),
        ("Accessoire soin élégant", 72_000, 8, "galaxy-earrings.jpg"),
        ("Pochette beauté nomade", 124_000, 13, "pink-purse.jpg"),
    ],
}


def main() -> None:
    storage = MinioProductImageStorage()
    with SessionLocal() as db:
        categories = {category.slug: category for category in db.scalars(select(ProductCategoryModel))}
        missing = sorted({row[5] for row in PRODUCTS} - categories.keys())
        if missing:
            raise RuntimeError(f"Required categories are missing; apply migrations first: {', '.join(missing)}")

        added = 0
        skipped = 0
        for code, name, description, price, quantity, slug, filename in PRODUCTS:
            if db.scalar(select(ProductModel.id).where(ProductModel.code == code)):
                skipped += 1
                continue

            image_path = IMAGE_ROOT / filename
            contents = image_path.read_bytes()
            image_key = storage.upload(contents, "image/jpeg")
            product = ProductModel(
                code=code,
                name=name,
                description=description,
                price=price,
                quantity=quantity,
                image_key=image_key,
                category_id=categories[slug].id,
                is_active=True,
            )
            db.add(product)
            try:
                db.commit()
                added += 1
            except Exception:
                db.rollback()
                storage.delete(image_key)
                raise

        for slug, items in PAGINATION_PRODUCTS.items():
            category = categories.get(slug)
            if category is None:
                continue

            active_count = db.scalar(
                select(func.count(ProductModel.id)).where(
                    ProductModel.category_id == category.id,
                    ProductModel.is_active.is_(True),
                )
            ) or 0
            for index, (name, price, quantity, filename) in enumerate(items, start=1):
                if active_count >= 13:
                    break
                code = f"DEMO-PAGE-{slug[:8].upper()}-{index:03d}"
                if db.scalar(select(ProductModel.id).where(ProductModel.code == code)):
                    continue
                db.add(
                    ProductModel(
                        code=code,
                        name=name,
                        description=f"{name}, sélectionné pour découvrir la catégorie {category.name.lower()}.",
                        price=price,
                        quantity=quantity,
                        image_url=f"/demo/images/product/{filename}",
                        category_id=category.id,
                        is_active=True,
                    )
                )
                active_count += 1
                added += 1

            db.commit()

        print(
            f"Catalogue de démonstration : {added} produit(s) ajouté(s), "
            f"{skipped} déjà présent(s). Chaque catégorie contient au moins 13 produits actifs."
        )


if __name__ == "__main__":
    main()
