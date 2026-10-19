"""Publica no bucket as bases geradas por scripts/build_data.py.

Uso:
    python scripts/upload_gcs.py              # confere, mostra o que muda e pede confirmação
    python scripts/upload_gcs.py --dry-run    # só mostra o que seria feito
    python scripts/upload_gcs.py --sim        # sem pergunta (rotinas automáticas)

Antes de enviar, compara a base nova com a que está no bucket e avisa se algum indicador perdeu anos, níveis
ou uma parte relevante dos valores (planilha incompleta, coluna renomeada ou apagada). Com perdas, pede uma
segunda confirmação; com --sim, só segue se vier também --aceitar-perdas.

O bucket e a pasta vêm de [gcs] em .streamlit/secrets.toml (ou de --bucket e --prefixo).
A credencial NÃO é a conta de leitura do painel: o envio precisa de permissão de escrita. Vale o login do
`gcloud auth login` (ou `gcloud auth application-default login`); ou informe --credenciais chave.json (ou GOOGLE_APPLICATION_CREDENTIALS).

Ordem de envio: dados.parquet, fichas.json e, por último, manifest.json. O painel só troca de versão quando o
manifest muda, então ele nunca lê um manifest novo apontando para dados que ainda não chegaram. Antes de
sobrescrever, a versão anterior é copiada para <pasta>/anteriores/<versão>/ para permitir voltar atrás.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
SECRETS = ROOT / ".streamlit" / "secrets.toml"
FILES = ["dados.parquet", "fichas.json", "manifest.json"]  # manifest por último
DROP_TOLERANCE = 0.02  # queda de até 2% nos valores de um indicador/ano/nível não é considerada perda
MAX_LINES = 25


def fail(msg: str):
    sys.exit(f"✗ {msg}")


def check_build() -> dict:
    """Confere se build/ está completo e coerente: o hash de dados+fichas deve bater com a versão do manifest."""
    missing = [f for f in FILES if not (BUILD_DIR / f).exists()]
    if missing:
        fail(f"faltam em {BUILD_DIR}: {', '.join(missing)}. Rode `python scripts/build_data.py` primeiro.")
    manifest = json.loads((BUILD_DIR / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((BUILD_DIR / "dados.parquet").read_bytes() + (BUILD_DIR / "fichas.json").read_bytes())
    if digest.hexdigest()[:12] != manifest["versao"]:
        fail("os arquivos de build/ não correspondem ao manifest.json (versão diferente). "
             "Rode `python scripts/build_data.py` de novo para gerar os três juntos.")
    return manifest


def find_losses(old_parquet: bytes | Path, new_parquet: bytes | Path) -> list[str]:
    """Compara a base publicada com a nova e lista o que sumiu: indicadores, anos, níveis ou parte dos valores."""
    import pandas as pd

    def counts(src):
        df = pd.read_parquet(io.BytesIO(src) if isinstance(src, bytes) else src, columns=["ind", "nivel", "ano", "valor"])
        df = df[df.valor.notna()]
        return df.groupby(["ind", "nivel", "ano"], observed=True).size()

    old, new = counts(old_parquet), counts(new_parquet)
    j = old.rename("antes").to_frame().join(new.rename("depois"), how="left").fillna({"depois": 0}).reset_index()
    j["ind"], j["nivel"] = j["ind"].astype(str), j["nivel"].astype(str)
    gone = set(j.ind) - set(new.reset_index()["ind"].astype(str))
    out = [f"{i}: indicador sem nenhum valor na base nova" for i in sorted(gone)]
    j = j[~j.ind.isin(gone)]
    for ind, g in j.groupby("ind"):
        parts = []
        for nivel, h in g.groupby("nivel"):
            lost = h[h.depois == 0]
            if len(lost):
                parts.append(f"{nivel}: perdeu {_years(lost.ano)}")
            drop = h[(h.depois > 0) & (h.depois < h.antes * (1 - DROP_TOLERANCE))]
            for r in drop.itertuples():
                parts.append(f"{nivel} {r.ano}: {int(r.antes)} → {int(r.depois)} valores")
        if parts:
            out.append(f"{ind}: " + "; ".join(parts))
    return out


def _years(years) -> str:
    ys = sorted(int(y) for y in years)
    runs, start = [], 0
    for k in range(1, len(ys) + 1):
        if k == len(ys) or ys[k] != ys[k - 1] + 1:
            runs.append(str(ys[start]) if k - start == 1 else f"{ys[start]}–{ys[k - 1]}")
            start = k
    return ", ".join(runs)


def bucket_config(args) -> tuple[str, str]:
    cfg = {}
    if SECRETS.exists():
        cfg = tomllib.loads(SECRETS.read_text(encoding="utf-8")).get("gcs", {})
    bucket = args.bucket or cfg.get("bucket")
    prefix = args.prefixo if args.prefixo is not None else cfg.get("prefix", "painel/")
    if not bucket:
        fail("bucket não definido: crie a seção [gcs] em .streamlit/secrets.toml ou use --bucket.")
    return bucket, prefix.strip("/")


def make_client(key_file: Path | None):
    """Cliente do Storage: chave JSON, credencial padrão (ADC) ou, na falta dela, o login ativo do gcloud."""
    from google.cloud import storage
    try:
        if key_file:
            return storage.Client.from_service_account_json(str(key_file))
        return storage.Client()
    except Exception as e:
        err = e
    try:  # `gcloud auth login` não cria a credencial padrão; reaproveita o token da conta ativa
        import subprocess
        from google.oauth2.credentials import Credentials
        token = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True,
                               check=True).stdout.strip()
        project = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True,
                                 text=True).stdout.strip() or None
        return storage.Client(credentials=Credentials(token), project=project)
    except Exception:
        fail(f"não foi possível autenticar no Google Cloud ({err}). Rode `gcloud auth login` ou "
             "`gcloud auth application-default login`, ou use --credenciais chave.json.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bucket", help="nome do bucket (padrão: [gcs].bucket de secrets.toml)")
    ap.add_argument("--prefixo", help="pasta no bucket (padrão: [gcs].prefix ou 'painel')")
    ap.add_argument("--credenciais", type=Path, help="chave JSON de uma conta com permissão de escrita")
    ap.add_argument("--dry-run", action="store_true", help="não envia nada, só mostra o plano")
    ap.add_argument("--sim", action="store_true", help="não pede confirmação")
    ap.add_argument("--aceitar-perdas", action="store_true",
                    help="com --sim, segue mesmo que a base nova tenha menos dados que a publicada")
    args = ap.parse_args()

    manifest = check_build()
    bucket_name, prefix = bucket_config(args)
    path = lambda name: f"{prefix}/{name}" if prefix else name

    client = make_client(args.credenciais)
    bucket = client.bucket(bucket_name)

    old_blob = bucket.blob(path("manifest.json"))
    old = json.loads(old_blob.download_as_bytes()) if old_blob.exists() else None

    print(f"Destino : gs://{bucket_name}/{prefix}/")
    print(f"No bucket: {('versão ' + old['versao'] + ' (' + old['gerado_em'] + ')') if old else 'vazio'}")
    print(f"A enviar : versão {manifest['versao']} (gerada em {manifest['gerado_em']}), "
          f"{len(manifest['indicadores'])} indicadores, planilha '{manifest['planilha']}'")
    if old:
        ids_old, ids_new = set(old.get("indicadores", [])), set(manifest["indicadores"])
        if ids_new - ids_old:
            print(f"  + entram : {', '.join(sorted(ids_new - ids_old))}")
        if ids_old - ids_new:
            print(f"  - saem   : {', '.join(sorted(ids_old - ids_new))}")
        if old["versao"] == manifest["versao"]:
            print("  = a versão do bucket já é esta; nada a fazer.")
            return
    for w in manifest.get("avisos", []):
        print(f"  aviso do build: {w}")

    losses = []
    if old:
        old_data = bucket.blob(path("dados.parquet"))
        if old_data.exists():
            losses = find_losses(old_data.download_as_bytes(), BUILD_DIR / "dados.parquet")
    if losses:
        print(f"\n⚠ A base nova tem MENOS dados que a publicada ({len(losses)} indicadores afetados):")
        for line in losses[:MAX_LINES]:
            print(f"  - {line}")
        if len(losses) > MAX_LINES:
            print(f"  … e mais {len(losses) - MAX_LINES}")
        print("  Confira se a planilha chegou completa e se nenhuma coluna foi renomeada ou apagada.")
    elif old:
        print("\nNenhuma perda de dados em relação à versão publicada.")
    if args.dry_run:
        print("\n(dry-run) nada foi enviado.")
        return
    if losses and args.sim and not args.aceitar_perdas:
        fail("há perdas de dados em relação à versão publicada; revise ou use --aceitar-perdas.")
    if not args.sim:
        if input("\nPublicar agora? [s/N] ").strip().lower() not in ("s", "sim", "y"):
            fail("cancelado; nada foi enviado.")
        if losses and input("Há perdas de dados (acima). Publicar mesmo assim? [s/N] ").strip().lower() not in ("s", "sim", "y"):
            fail("cancelado; nada foi enviado.")

    if old:  # guarda a versão atual antes de sobrescrever
        backup = f"{prefix}/anteriores/{old['versao']}" if prefix else f"anteriores/{old['versao']}"
        for name in FILES:
            src = bucket.blob(path(name))
            if src.exists():
                bucket.copy_blob(src, bucket, f"{backup}/{name}")
        print(f"Versão anterior copiada para gs://{bucket_name}/{backup}/")
    for name in FILES:
        bucket.blob(path(name)).upload_from_filename(str(BUILD_DIR / name))
        print(f"  enviado {name}")

    new = json.loads(bucket.blob(path("manifest.json")).download_as_bytes())
    if new["versao"] != manifest["versao"]:
        fail("o manifest no bucket não confere com o enviado; confira o bucket.")
    print(f"\nOK — versão {manifest['versao']} publicada. O painel a carrega em até 10 minutos.")


if __name__ == "__main__":
    main()
