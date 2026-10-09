"""Insert a small, repeatable showcase catalog with images stored in MinIO."""

from pathlib import Path

from sqlalchemy import select

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

        print(f"Catalogue de démonstration : {added} produit(s) ajouté(s), {skipped} déjà présent(s).")


if __name__ == "__main__":
    main()
