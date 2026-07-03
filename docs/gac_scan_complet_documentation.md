# Documentation Complète : Données GAC & Stratégie de Collecte

> Dossier : `docs/` | Dernière mise à jour : Juillet 2026  
> Projet : Bot-SWGOH | Basé sur : Comlink, swgoh-utils, recherches communautaires

---

## 1. La Vérité sur les Données GAC — Ce qui existe vraiment

### 1.1 Ce que Comlink expose (et ce qu'il n'expose pas)

Comlink est un proxy qui expose les mêmes APIs que le client mobile du jeu. Capital Games contrôle strictement ce qui est accessible.

**✅ Données disponibles via Comlink :**

| Endpoint | Ce qu'on obtient |
|---|---|
| `POST /player` | Roster complet, reliques, mods, rating GAC, 3 dernières saisons |
| `POST /getLeaderboard` (type `4`) | Tous les joueurs d'un bracket GAC **pendant GAC actif** |
| `POST /getLeaderboard` (type `6`) | Top 50 joueurs par ligue/division (toujours disponible) |
| `POST /getEvents` | Événements en cours (pour trouver l'ID du GAC actif) |
| `POST /getGuild` | Profil et membres d'une guilde |

**❌ Données NON disponibles via Comlink (ou toute API publique) :**

| Donnée | Raison |
|---|---|
| Équipes posées en défense | Données côté serveur CG, non exposées |
| Équipes utilisées en attaque | Données côté serveur CG, non exposées |
| Banners marqués par round | Idem |
| Résultat match par match | Idem |
| `wins` / `losses` dans `seasonStatus` | Champs présents mais **INACTIVE** — toujours à 0 |
| Historique GAC > 3 saisons | Limité côté API à 3 saisons |

---

### 1.2 Le mystère swgoh.gg — Comment obtiennent-ils les données de combat ?

> [!IMPORTANT]
> **swgoh.gg N'EST PAS un partenaire officiel de Capital Games.** Ils le disent eux-mêmes dans le footer de chaque page : "Not affiliated with EA, Capital Games, Disney or Lucasfilm Ltd."

**La vraie réponse :** swgoh.gg utilise exactement les **mêmes APIs de base que Comlink** (le jeu utilise Protocol Buffers / protobuf pour sa communication réseau). Mais ils ont deux avantages que nous n'avons pas :

#### Le mécanisme du "Player ID Sync"

Quand un joueur "sync" son compte sur swgoh.gg, il fournit son **Player ID** (un GUID interne, différent du ally code). swgoh.gg utilise ce Player ID pour appeler des endpoints **authentifiés** côté CG qui retournent les données de combat **du compte du joueur**.

```
Joueur → Donne son Player ID à swgoh.gg
swgoh.gg → Appelle l'API CG avec ce Player ID comme "contexte"
API CG → Retourne les logs de bataille GAC pour ce joueur spécifique
swgoh.gg → Stocke et affiche les données
```

Ces endpoints authentifiés **existent bien** dans le protocole du jeu (ils sont utilisés pour afficher l'historique en jeu), mais :
- Ils nécessitent l'authentification du compte du joueur (son Player ID ou token de session)
- Comlink ne les expose pas car il fonctionne sur des **comptes anonymes invités**
- Accéder à ces endpoints pour un autre joueur sans son consentement serait contraire aux CGU

#### L'échelle de swgoh.gg

swgoh.gg a accumulé des données depuis des **années** avec des **millions de comptes synchronisés** :
- Chaque joueur synced = accès à ses logs de combat
- Scan périodique de tous les profils publics
- ~15M+ combats GAC capturés par saison
- Base de données historique sur 5+ ans

#### Ce que ça signifie pour nous

| Ce que swgoh.gg peut faire | Ce qu'on peut faire |
|---|---|
| Données de combat réelles (équipes, banners) | Rosters des joueurs (Comlink brackets) |
| Win rates / Hold rates précis | Prédiction basée sur roster |
| Historique complet multi-saisons | Scan bracket (8 jours/saison) |
| ~15M combats/saison | ~300K rosters/saison (scan total) |

---

## 2. Les Sources de Données Disponibles

### Source A — Top 50 Leaderboard (Toujours disponible)

```python
# Disponible 24h/24, 7j/7, même hors GAC
POST /getLeaderboard
{
  "payload": {
    "leaderboardType": 6,
    "league": 100,    # 100 = Kyber
    "division": 25    # 25 = Division 1
  }
}
```

- **Volume :** 50 joueurs × 25 combinaisons = 1,250 joueurs max
- **Fréquence possible :** Quotidienne
- **Donnée :** Player IDs → requêtes `/player` pour les rosters

### Source B — Scan Brackets GAC (Pendant GAC actif uniquement)

```python
# Pendant les ~8 jours de GAC actif
POST /getLeaderboard
{
  "payload": {
    "leaderboardType": 4,
    "eventInstanceId": "CHAMPIONSHIPS_GA2_SEASON_42:O1718000000",
    "groupId": "...:KYBER:0"  # Bracket 0 de Kyber
  }
}
```

- **Volume :** ~37,500 brackets × 8 joueurs = ~300,000 joueurs
- **Fréquence :** 1 fois par GAC (toutes les 2 semaines)
- **Donnée :** Player IDs de tous les joueurs actifs dans toutes les ligues

### Source C — Auto-report des joueurs (Continu)

Via les commandes Discord du bot, les joueurs rapportent manuellement leurs combats.

- **Volume :** Dépend de l'adoption
- **Fréquence :** Continue
- **Donnée :** Données de combat RÉELLES (équipes, résultats, banners)

---

## 3. Calcul de Faisabilité — Scan Total Toutes Ligues

### 3.1 Estimation du volume

| Ligue | % joueurs | Nb joueurs | Nb brackets (÷8) |
|---|---|---|---|
| Carbonite | ~50% | ~150,000 | ~18,750 |
| Bronzium | ~25% | ~75,000 | ~9,375 |
| Chromium | ~15% | ~45,000 | ~5,625 |
| Aurodium | ~7% | ~21,000 | ~2,625 |
| Kyber | ~3% | ~9,000 | ~1,125 |
| **TOTAL** | 100% | **~300,000** | **~37,500** |

### 3.2 Durée du scan

| Phase | Opération | Rate limit | Durée |
|---|---|---|---|
| Phase 1 | Scanner ~37,500 brackets | 10 req/sec | ~62 min |
| Phase 2 | Récupérer ~300,000 rosters | 30 req/sec | ~2.7h |
| **TOTAL** | | | **~4 heures** |

> [!WARNING]
> **Rate limits Capital Games :**
> - Global : ~20 req/sec toutes requêtes confondues
> - `/player` spécifiquement : jusqu'à ~100 req/sec
> - Recommandé pour rester safe : **10-30 req/sec**
> - Risque de ban IP si dépassement

### 3.3 Stockage estimé

| Mode de stockage | Taille/joueur | Total 300K joueurs |
|---|---|---|
| JSON brut complet | ~50-100 KB | 15-30 GB |
| Données réduites (IDs + reliques) | ~2-5 KB | **600 MB - 1.5 GB** ✅ |
| Ultra-réduit (R5+ uniquement) | < 1 KB | < 300 MB |

**Recommandation :** Stocker uniquement les données utiles (mode réduit), SQLite est suffisant.

---

## 4. Tableau de Comparaison Final

| Critère | swgoh.gg | Notre Bot (scan total) | Notre Bot (Top 50) |
|---|---|---|---|
| **Source** | Sync + protobuf authentifié | Comlink brackets | Comlink leaderboard |
| **Volume** | 15M+ combats/saison | ~300K rosters | ~1,250 rosters |
| **Équipes défense** | ✅ Réelles | ❌ Prédiction | ❌ Prédiction |
| **Win/Hold rates** | ✅ Réels | ❌ Non calculable | ❌ Non calculable |
| **Banners** | ✅ Réels | ❌ Non disponible | ❌ Non disponible |
| **Disponibilité** | Permanente | ⚠️ 8j / 2 semaines | ✅ Permanente |
| **Toutes ligues** | ✅ | ✅ | ⚠️ (Top 50/division) |
| **Données roster** | ✅ | ✅ | ✅ |
| **Évolution méta** | ✅ Historique 5+ ans | ✅ Si on stocke | ✅ Si on stocke |
| **Risque légal/ban** | Faible (sync volontaire) | Faible (public) | Très faible |

---

## 5. Ce qu'on peut construire avec ces données

### 5.1 Avec le scan brackets (300K rosters)

```
✅ Savoir que "SLKR est dans 78% des rosters Kyber D1"
✅ Savoir que "Jabba est dans 45% des rosters Aurodium"
✅ Voir l'évolution méta saison par saison
✅ Pré-charger le roster d'un adversaire avant qu'un joueur le demande
✅ Calculer la "popularité" de chaque personnage par ligue
⚠️ Prédire (non certifier) les équipes posées en défense
❌ Connaître le résultat de vrais combats
```

### 5.2 Avec l'auto-report (données joueurs)

```
✅ Win rates réels : "SLKR contre Jabba : 78% de win (18/23)"
✅ Savoir quelles équipes les joueurs utilisent vraiment en attaque
✅ Historique de progression d'un joueur saison par saison
✅ Données 100% fiables pour la recommandation de contres
✅ Base de données unique à votre communauté
```

### 5.3 Combinés : Recommandation optimale

```
Joueur : /gac-counter JABBA 5v5

Bot :
1. Vérifie si le joueur a SLKR au bon niveau (Comlink /player)
2. Consulte counter_performance :
   → "SLKR vs Jabba : 18 wins / 5 losses = 78% (23 combats reportés)"
3. Consulte le scan méta :
   → "Jabba est dans 67% des rosters Kyber D1 cette saison"
4. Propose SLKR avec niveau de confiance affiché
5. Si le joueur n'a pas SLKR → propose le meilleur contre disponible
```
