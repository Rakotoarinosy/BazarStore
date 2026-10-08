"""Données fictives pour le développement et les tests manuels (base locale).

Usage : `make seed` (ou `python -m src.infrastructure.persistence.seed`).
Prérequis : `make migrate`. Le script est rejouable : il supprime d'abord les données qu'il a
lui-même créées (citoyens et agents en @seed.test, et leurs demandes), puis les recrée.
Tirage aléatoire à graine fixe : les mêmes données à chaque exécution (hors dates, relatives à
aujourd'hui pour que le dashboard « 7 derniers jours » soit toujours rempli).
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, inspect, or_, select
from sqlalchemy.orm import Session

from src.domain.citizen_request import RequestCategory, RequestPriority, RequestStatus
from src.infrastructure.persistence.database import SessionLocal, engine
from src.infrastructure.persistence.models import (
    AgentModel,
    CitizenRequestModel,
    UserModel,
    new_id,
)

SEED_EMAIL_DOMAIN = "seed.test"
REQUEST_COUNT = 120

CITIZENS = [
    "Rija Andrianaivo",
    "Hanitra Rakotomalala",
    "Tahina Randriamampionona",
    "Voahangy Rasoanaivo",
    "Mamy Razafindrakoto",
    "Fanja Ravelojaona",
    "Tojo Rakotondrabe",
    "Lalaina Andriamanantena",
    "Nirina Ramanantsoa",
    "Haja Rabemananjara",
    "Soa Randrianarisoa",
    "Toky Razanajatovo",
    "Miora Rajaonarison",
    "Faly Andrianjafy",
    "Onja Ratsimbazafy",
]

# (nom, département, statut, actif) : un agent désactivé pour tester ce cas.
AGENTS = [
    ("Jean Rakoto", "Voirie", "available", True),
    ("Sarah Andry", "Eau", "in_intervention", True),
    ("Marc Rabe", "Éclairage public", "available", True),
    ("Sitraka Rabearivelo", "Déchets", "in_intervention", True),
    ("Andry Ramaroson", "Sécurité", "unavailable", True),
    ("Volana Rakotovao", "Espaces verts", "offline", False),
]

# (adresse, latitude, longitude) : centres approximatifs des quartiers d'Antananarivo.
LOCATIONS = [
    ("Analakely, avenue de l'Indépendance", -18.9068, 47.5244),
    ("Isoraka, rue Ramelina", -18.9139, 47.5186),
    ("Antaninarenina, place de l'Indépendance", -18.9095, 47.526),
    ("Ambohijatovo, jardin", -18.911, 47.529),
    ("Behoririka, rue Rainitovo", -18.899, 47.525),
    ("Tsaralalana, rue Ratsimilaho", -18.903, 47.52),
    ("Anosy, bord du lac", -18.9175, 47.5195),
    ("Ampefiloha, cité 67 Ha", -18.912, 47.511),
    ("Andravoahangy, marché", -18.894, 47.531),
    ("Ankadifotsy, rue Andriamasinavalona", -18.8985, 47.533),
    ("Ambanidia, route circulaire", -18.92, 47.535),
    ("Ankorondrano, rue Ravoninahitriniarivo", -18.879, 47.524),
    ("Ivandry, route des Hydrocarbures", -18.872, 47.53),
    ("Ambohipo, cité universitaire", -18.923, 47.553),
    ("Ankatso, campus", -18.916, 47.56),
    ("Andoharanofotsy, RN7", -18.98, 47.535),
    ("Itaosy, route d'Arivonimamo", -18.915, 47.475),
    ("Mahamasina, stade", -18.919, 47.524),
    ("Faravohitra, escaliers", -18.903, 47.531),
    ("Isotry, rue du marché", -18.908, 47.513),
    ("Anosibe, grand marché", -18.928, 47.51),
    ("Ambohimanarina, gare", -18.875, 47.508),
    ("Ampasampito, bypass", -18.897, 47.55),
    ("67 Ha Nord, bloc 12", -18.905, 47.508),
]

# Scénarios réalistes par catégorie : (titre, description).
SCENARIOS: dict[RequestCategory, list[tuple[str, str]]] = {
    RequestCategory.PUBLIC_LIGHTING: [
        (
            "Lampadaire éteint",
            "Le lampadaire devant le numéro 12 ne fonctionne plus depuis une semaine. "
            "La rue est totalement dans le noir le soir.",
        ),
        (
            "Éclairage clignotant",
            "Plusieurs lampadaires clignotent en continu, ça gêne les riverains la nuit.",
        ),
        (
            "Poteau électrique penché",
            "Un poteau d'éclairage penche dangereusement après les fortes pluies.",
        ),
        (
            "Quartier sans éclairage",
            "Toute la ruelle est sans lumière depuis la coupure de mardi, "
            "les habitants ont peur de sortir le soir.",
        ),
    ],
    RequestCategory.ROADS: [
        (
            "Nid-de-poule dangereux",
            "Un grand nid-de-poule s'est formé au milieu de la chaussée, "
            "plusieurs motos ont déjà chuté.",
        ),
        (
            "Trottoir effondré",
            "Une partie du trottoir s'est effondrée dans le caniveau, passage piéton impossible.",
        ),
        (
            "Route inondée",
            "La route est inondée à chaque pluie, l'eau ne s'évacue pas.",
        ),
        (
            "Signalisation arrachée",
            "Le panneau stop à l'intersection a été arraché, risque d'accident.",
        ),
        (
            "Dos d'âne demandé",
            "Les voitures roulent très vite devant l'école primaire, "
            "nous demandons l'installation d'un ralentisseur.",
        ),
    ],
    RequestCategory.WATER: [
        (
            "Fuite d'eau sur la voie publique",
            "Une canalisation fuit depuis trois jours, l'eau coule en permanence sur la route.",
        ),
        (
            "Borne-fontaine hors service",
            "La borne-fontaine du quartier ne donne plus d'eau, "
            "les familles doivent marcher loin pour s'approvisionner.",
        ),
        (
            "Égout bouché",
            "Le regard d'égout déborde et dégage une forte odeur.",
        ),
        (
            "Eau trouble au robinet",
            "L'eau du réseau est marron depuis hier matin dans plusieurs maisons.",
        ),
    ],
    RequestCategory.WASTE: [
        (
            "Dépôt sauvage d'ordures",
            "Un tas d'ordures s'accumule au coin de la rue, il attire les rats.",
        ),
        (
            "Bac à ordures plein",
            "Le bac collectif n'a pas été vidé depuis plus d'une semaine.",
        ),
        (
            "Déchets dans le canal",
            "Le canal est obstrué par des sacs plastiques, risque d'inondation.",
        ),
        (
            "Gravats abandonnés",
            "Des gravats de chantier ont été déposés sur le trottoir.",
        ),
    ],
    RequestCategory.SAFETY: [
        (
            "Câble électrique à terre",
            "Un câble est tombé sur le trottoir après l'orage, danger immédiat pour les enfants.",
        ),
        (
            "Mur menaçant de s'effondrer",
            "Le mur de soutènement se fissure au-dessus de la ruelle.",
        ),
        (
            "Regard sans couvercle",
            "Un regard est ouvert sans couvercle sur le trottoir, quelqu'un pourrait tomber.",
        ),
        (
            "Arbre prêt à tomber",
            "Un gros arbre penche au-dessus des habitations et de la route.",
        ),
    ],
    RequestCategory.GREEN_SPACES: [
        (
            "Herbes hautes dans le jardin public",
            "Le jardin n'est plus entretenu, les herbes dépassent un mètre.",
        ),
        (
            "Banc cassé",
            "Deux bancs du parc sont cassés et dangereux.",
        ),
        (
            "Branches à élaguer",
            "Des branches touchent les fils électriques le long de l'allée.",
        ),
        (
            "Aire de jeux dégradée",
            "La balançoire de l'aire de jeux est cassée.",
        ),
    ],
    RequestCategory.OTHER: [
        (
            "Nuisances sonores",
            "Un bar diffuse de la musique très fort tous les soirs jusqu'à 2h du matin.",
        ),
        (
            "Animaux errants",
            "Une meute de chiens errants effraie les passants près de l'arrêt de bus.",
        ),
        (
            "Affichage sauvage",
            "Les murs de l'école sont couverts d'affiches collées illégalement.",
        ),
    ],
}

# Pondérations pour obtenir une répartition crédible sur le dashboard.
CATEGORY_WEIGHTS = {
    RequestCategory.PUBLIC_LIGHTING: 18,
    RequestCategory.ROADS: 25,
    RequestCategory.WATER: 15,
    RequestCategory.WASTE: 20,
    RequestCategory.SAFETY: 8,
    RequestCategory.GREEN_SPACES: 8,
    RequestCategory.OTHER: 6,
}
PRIORITY_WEIGHTS = {
    RequestPriority.LOW: 20,
    RequestPriority.NORMAL: 45,
    RequestPriority.HIGH: 25,
    RequestPriority.URGENT: 10,
}
STATUS_WEIGHTS = {
    RequestStatus.NEW: 30,
    RequestStatus.IN_PROGRESS: 25,
    RequestStatus.PENDING: 10,
    RequestStatus.RESOLVED: 28,
    RequestStatus.REJECTED: 7,
}


def _pick[T](rng: random.Random, weights: dict[T, int]) -> T:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _slug(name: str) -> str:
    return ".".join(name.lower().split())


def _clear_seed_data(db: Session) -> None:
    seed_user_ids = select(UserModel.id).where(UserModel.email.like(f"%@{SEED_EMAIL_DOMAIN}"))
    seed_agent_ids = select(AgentModel.id).where(AgentModel.email.like(f"%@{SEED_EMAIL_DOMAIN}"))
    db.execute(
        delete(CitizenRequestModel).where(
            or_(
                CitizenRequestModel.citizen_id.in_(seed_user_ids),
                CitizenRequestModel.assigned_agent_id.in_(seed_agent_ids),
            )
        )
    )
    db.execute(delete(AgentModel).where(AgentModel.email.like(f"%@{SEED_EMAIL_DOMAIN}")))
    db.execute(delete(UserModel).where(UserModel.email.like(f"%@{SEED_EMAIL_DOMAIN}")))


def _build_request(
    rng: random.Random, now: datetime, citizen_ids: list[str], agent_ids: list[str]
) -> CitizenRequestModel:
    category = _pick(rng, CATEGORY_WEIGHTS)
    title, description = rng.choice(SCENARIOS[category])
    location, latitude, longitude = rng.choice(LOCATIONS)
    status = _pick(rng, STATUS_WEIGHTS)

    # 60 % des demandes sur les 7 derniers jours pour alimenter la courbe du dashboard.
    max_days = 7 if rng.random() < 0.6 else 45
    created_at = now - timedelta(days=rng.uniform(0, max_days))

    # Toute demande prise en charge a un agent ; 20 % des nouvelles sont déjà pré-attribuées.
    is_handled = status in (
        RequestStatus.IN_PROGRESS,
        RequestStatus.PENDING,
        RequestStatus.RESOLVED,
    )
    is_preassigned = status is RequestStatus.NEW and rng.random() < 0.2
    assigned_agent_id = rng.choice(agent_ids) if is_handled or is_preassigned else None

    resolved_at = None
    if status is RequestStatus.RESOLVED:
        elapsed = now - created_at
        resolved_at = created_at + elapsed * rng.uniform(0.2, 1.0)

    return CitizenRequestModel(
        id=new_id(),
        title=f"{title} — {location.split(',')[0]}",
        description=description,
        category=category.value,
        priority=_pick(rng, PRIORITY_WEIGHTS).value,
        status=status.value,
        citizen_id=rng.choice(citizen_ids),
        created_at=created_at,
        location=location,
        # Petit décalage (~300 m) pour que les demandes d'un même quartier ne se superposent pas.
        latitude=latitude + rng.uniform(-0.003, 0.003),
        longitude=longitude + rng.uniform(-0.003, 0.003),
        assigned_agent_id=assigned_agent_id,
        resolved_at=resolved_at,
    )


def _build_resolved_today(
    rng: random.Random, now: datetime, citizen_ids: list[str], agent_ids: list[str], count: int
) -> list[CitizenRequestModel]:
    """Quelques demandes résolues aujourd'hui, pour la tuile « interventions du jour »."""
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    requests = []
    for _ in range(count):
        request = _build_request(rng, now, citizen_ids, agent_ids)
        request.status = RequestStatus.RESOLVED.value
        request.assigned_agent_id = rng.choice(agent_ids)
        request.resolved_at = today_start + (now - today_start) * rng.uniform(0.1, 1.0)
        request.created_at = request.resolved_at - timedelta(days=rng.uniform(0.5, 5))
        requests.append(request)

    return requests


def seed(db: Session) -> dict[str, int]:
    tables = set(inspect(db.get_bind()).get_table_names())
    required = {
        UserModel.__tablename__,
        AgentModel.__tablename__,
        CitizenRequestModel.__tablename__,
    }
    missing = required - tables
    if missing:
        raise SystemExit(f"Tables absentes : {sorted(missing)}. Lancer d'abord `make migrate`.")

    rng = random.Random(42)
    now = datetime.now(UTC)
    _clear_seed_data(db)

    citizens = [
        UserModel(
            id=new_id(),
            email=f"{_slug(name)}@{SEED_EMAIL_DOMAIN}",
            name=name,
            created_at=now - timedelta(days=rng.randint(30, 365)),
        )
        for name in CITIZENS
    ]
    agents = [
        AgentModel(
            id=new_id(),
            email=f"{_slug(name)}@{SEED_EMAIL_DOMAIN}",
            name=name,
            department=department,
            status=status,
            is_active=is_active,
            created_at=now - timedelta(days=rng.randint(90, 730)),
        )
        for name, department, status, is_active in AGENTS
    ]
    db.add_all(citizens)
    db.add_all(agents)
    db.flush()

    citizen_ids = [user.id for user in citizens]
    # On n'attribue des demandes qu'aux agents actifs, comme l'impose l'API.
    agent_ids = [agent.id for agent in agents if agent.is_active]
    requests = [_build_request(rng, now, citizen_ids, agent_ids) for _ in range(REQUEST_COUNT)]
    requests += _build_resolved_today(rng, now, citizen_ids, agent_ids, count=5)
    db.add_all(requests)
    db.commit()

    return {
        "citoyens": len(citizens),
        "agents": len(agents),
        "demandes citoyennes": len(requests),
    }


def main() -> None:
    print(f"Base : {engine.url}")
    with SessionLocal() as db:
        counts = seed(db)
    for label, count in counts.items():
        print(f"  {count:>4} {label}")


if __name__ == "__main__":
    main()
