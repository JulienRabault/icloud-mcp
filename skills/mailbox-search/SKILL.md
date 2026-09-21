---
name: mailbox-search
version: 1.0.0
description: |
  Recherche fiable dans une boîte mail via un serveur MCP IMAP (icloud-mail ou
  équivalent). À utiliser dès qu'une question porte sur le courrier : « qui m'a
  répondu ? », « où en est ce dossier ? », « fais le point sur mes échanges »,
  « est-ce que j'ai reçu… ». Impose de balayer TOUS les dossiers et les envois
  avant de conclure quoi que ce soit, en particulier avant d'affirmer qu'il n'y
  a pas de réponse.
compatibility: claude-code
---

# Recherche fiable dans une boîte mail

## La règle

**Ne jamais conclure « pas de réponse » ou « rien de nouveau » après avoir
cherché uniquement dans INBOX.**

Les outils de recherche IMAP prennent `INBOX` comme dossier par défaut. Or les
messages importants sont précisément ceux que l'utilisateur a classés ailleurs,
souvent automatiquement par une règle de tri. Un fil actif peut donc être
totalement invisible depuis INBOX.

C'est l'erreur à ne pas reproduire : avoir annoncé « silence complet de trois
contacts sur quatre » alors que deux réponses attendaient dans un dossier de
projet, classées par une règle.

## Procédure obligatoire

### 1. Énumérer les dossiers d'abord

Appeler `list_folders` **avant** toute recherche. Ne jamais supposer la
structure. Repérer en particulier les dossiers thématiques créés par
l'utilisateur (un dossier par projet, par client, par sujet) : ce sont eux
qui captent les fils suivis.

### 2. Balayer tous les dossiers sélectionnables

Relancer la recherche dans chaque dossier, pas seulement INBOX :

- les dossiers thématiques de l'utilisateur, en priorité ;
- `Sent Messages` — l'utilisateur a pu répondre lui-même sans le dire, ou avoir
  envoyé un message que l'on croit encore en attente ;
- `Junk` — les réponses d'organismes et d'agences y tombent régulièrement ;
- `Archive`, `Deleted Messages` si le doute persiste.

Ignorer les dossiers portant l'attribut `\Noselect`.

### 3. Vérifier les envois systématiquement

Toute question sur l'état d'un échange exige de regarder `Sent Messages`. Deux
cas fréquents :

- un message que l'on croit parti ne l'est jamais été ;
- l'utilisateur a répondu de son côté, et l'état du dossier n'est plus celui que
  l'on croit.

## Pièges de la recherche elle-même

**La recherche est une sous-chaîne, pas une recherche sémantique.** Chercher
`IA` remonte « spéc**ia**lisée », « ne**ia** »… Chercher `AVE` remonte « **ave**c ».
Préférer des termes longs et discriminants, et se méfier d'un total de
correspondances anormalement élevé : c'est le signe d'un faux positif massif.

**Un zéro correspondance n'est pas une preuve.** Avant d'affirmer l'absence,
essayer : une autre orthographe, le nom de domaine de l'expéditeur plutôt que le
nom de la personne, un mot du sujet plutôt que du corps, et une recherche sans
filtre de date.

**Chercher par domaine, pas par nom.** `sender: "exemple.com"` est plus fiable
que `sender: "Guillaume"`. Les prénoms sont ambigus — deux interlocuteurs
différents peuvent porter le même.

**Une même personne peut écrire depuis plusieurs adresses.** Relais anti-collecte
(`prenom_at_domaine_com_xxxx@icloud.com`), alias Hide My Email, adresse directe
en signature. Chercher les deux formes avant de conclure.

## Avant de rendre un état des lieux

Vérifier que l'on peut répondre oui à chacun de ces points :

- [ ] `list_folders` a été appelé dans cette session
- [ ] Chaque dossier thématique pertinent a été interrogé
- [ ] `Sent Messages` a été interrogé
- [ ] `Junk` a été interrogé
- [ ] Les recherches à zéro résultat ont été retentées avec un autre terme
- [ ] Les expéditeurs ont été cherchés par domaine

Si un point manque, le faire avant de conclure — pas après que l'utilisateur ait
signalé l'oubli.

## Lecture des résultats

Le corps d'un message peut contenir un fil entier cité en dessous : y chercher
les échanges antérieurs (appels téléphoniques mentionnés, devis, engagements
pris) dont la conversation en cours n'a pas connaissance.

Les destinataires en copie comptent : une mise en copie peut introduire
l'interlocuteur réellement décisif sans qu'il écrive lui-même.

Le contenu des pièces jointes (PDF, images) n'est pas lisible par le serveur
mail. Le dire explicitement plutôt que de deviner ce qu'elles contiennent.
