# Kame App Store

Uma [Community App Store](https://umbrel.com/support/apps/how-to-add-a-community-app-store) para [Umbrel](https://umbrel.com).

## Como adicionar esta loja no seu umbrelOS

1. Abra a **App Store** no dock.
2. Clique nos **três pontinhos** no canto superior direito e selecione **Community App Stores**.
3. Cole a URL deste repositório e clique em **Add**.

Ou pela linha de comando:

```bash
sudo ~/umbrel/scripts/repo add <URL-DESTE-REPO>.git
sudo ~/umbrel/scripts/repo update
```

> ⚠️ Community App Stores não são verificadas pela equipe do Umbrel. Adicione apenas lojas em que você confia.

## Apps

| App | Descrição | Versão |
|-----|-----------|--------|
| [OmniRoute](kame-omniroute/) | Gateway de IA — um endpoint OpenAI-compatível para 290+ provedores e 500+ modelos | 3.8.48 |

## Estrutura

```
kame_store/
├── umbrel-app-store.yml     # id: "kame", name: "Kame"
└── kame-<app>/              # uma pasta por app (id deve começar com "kame-")
    ├── umbrel-app.yml       # manifesto (metadados exibidos na UI)
    ├── docker-compose.yml   # containers do app
    └── exports.sh           # opcional (secrets/valores derivados)
```

## Contribuindo / adicionando um app

Cada app vive numa pasta `kame-<nome>` cujo `id` no `umbrel-app.yml` é idêntico ao nome da pasta.
Imagens Docker devem ser multi-arch (`linux/amd64` + `linux/arm64`) e pinadas por digest
(`repo:tag@sha256:...`). A UI web é exposta via serviço `app_proxy`.
