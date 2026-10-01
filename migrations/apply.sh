#!/bin/sh
# Apply every migration in order. The embedding dimension is passed as a
# psql variable so the vector column follows EMBEDDING_DIM.
set -eu

for file in /migrations/*.sql; do
    psql -v ON_ERROR_STOP=1 \
        -v embedding_dim="${EMBEDDING_DIM:?EMBEDDING_DIM must be set}" \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$file"
done
