#!/bin/bash
set -e

detach_str=""
while (( "$#" )); do
    case "$1" in
        -d|--detach)
            echo "--detach 模式"
            detach_str="-d"
            shift
            ;;
        -?*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

project_path="./"
if [ -n "$1" ]; then
    project_path="$1"
fi
if [[ ! $project_path =~ /$ ]]; then
    project_path=$project_path/
fi

export PROJECT_NAME=$(sed -n "s/^[[:space:]]*name[[:space:]]*=[[:space:]]*['\"]\([^'\"]*\)['\"].*/\1/p" ${project_path}pyproject.toml)
export PROJECT_VERSION=$(sed -n "s/^[[:space:]]*version[[:space:]]*=[[:space:]]*['\"]\([^'\"]*\)['\"].*/\1/p" ${project_path}pyproject.toml)

# Guard: image must exist
if ! docker image inspect ${PROJECT_NAME}:${PROJECT_VERSION} > /dev/null 2>&1; then
    echo "❌ 找不到 image ${PROJECT_NAME}:${PROJECT_VERSION}"
    echo "   請先執行 ./build.sh 來建立 image"
    exit 1
fi

# Guard: .env must exist
if [ ! -f "${project_path}.env" ]; then
    echo "❌ 找不到 .env 檔案"
    echo "   請複製 .env.example 並填入 Supabase 設定："
    echo "     cp .env.example .env"
    exit 1
fi

LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null \
    || ipconfig getifaddr en1 2>/dev/null \
    || echo "127.0.0.1")

if [ -n "$detach_str" ]; then
    echo "🚀 Starting app container (detached)..."
    docker compose up -d app
    echo ""
    echo "  本機：http://localhost:8001"
    echo "  區網：http://$LOCAL_IP:8001"
    echo ""
    echo "⚠️  背景模式：防睡眠未啟用。如需防止 Mac 休眠，請在另一個 Terminal 執行："
    echo "     caffeinate -i"
else
    echo "🚀 Starting (防睡眠已啟用，關閉此 Terminal 即停止)..."
    echo "  本機：http://localhost:8001"
    echo "  區網：http://$LOCAL_IP:8001"
    exec caffeinate -di docker compose up app
fi
