#!/usr/bin/env python3
"""
期權倉數儀表板 - 自動發布模組 (deploy_dashboard.py)
整合至 daily_update.py，每日收盤或定時入數後一鍵發布至網頁。

支援發布目標：
  1. Cloudflare Pages (推薦：全球 CDN、零下載、支援 Zero Trust 密碼鎖)
  2. GitHub Pages (Git 自動 commit & push)
  3. 本地 / 內網目錄同步 (Local Dist Directory)
"""
import os
import sys
import shutil
import subprocess
from datetime import datetime

# 目錄與路徑設置
BASE_DIR = os.path.expanduser('~/workspace')
HSI_DIR = os.path.join(BASE_DIR, 'your_files', 'hsioptions')
DIST_DIR = os.path.join(BASE_DIR, 'dist')

# 主儀表板候選來源（優先發布合併版，若無則降級為單頁版）
CANDIDATE_SOURCES = [
    os.path.join(HSI_DIR, '期權倉數儀表板.html'),
    os.path.join(HSI_DIR, 'options-dashboard.html'),
    os.path.join(HSI_DIR, '恆指期權倉數儀表板.html'),
]

# 附帶發布的子頁面
SUB_PAGES = {
    'stock.html': os.path.join(HSI_DIR, '股票期權倉數儀表板.html'),
    'strategy.html': os.path.join(HSI_DIR, '策略勝率儀表板.html'),
    'daily_points.html': os.path.join(HSI_DIR, '期權倉影-每日要點.html'),
    'strategy_ref.html': os.path.join(HSI_DIR, '期權倉影-明日策略參考.html'),
}

DEFAULT_CF_PROJECT = os.environ.get('CF_PAGES_PROJECT', 'hsi-options-radar')
DEFAULT_CF_BRANCH = os.environ.get('CF_PAGES_BRANCH', 'main')


def prepare_dist(log_fn=print):
    """整理 dist/ 發布目錄，將最新主儀表板轉存為 index.html"""
    os.makedirs(DIST_DIR, exist_ok=True)
    
    src_file = None
    for cand in CANDIDATE_SOURCES:
        if os.path.exists(cand) and os.path.getsize(cand) > 1000:
            src_file = cand
            break
            
    if not src_file:
        log_fn(f"[DEPLOY ERROR] 找不到有效的主體儀表板 HTML，候選清單：{CANDIDATE_SOURCES}")
        return False
        
    index_path = os.path.join(DIST_DIR, 'index.html')
    shutil.copyfile(src_file, index_path)
    file_size_mb = os.path.getsize(index_path) / (1024 * 1024)
    log_fn(f"[DEPLOY] 已複製 {os.path.basename(src_file)} -> dist/index.html ({file_size_mb:.2f} MB)")
    
    # 複製子頁面
    for target_name, sub_path in SUB_PAGES.items():
        if os.path.exists(sub_path) and os.path.getsize(sub_path) > 500:
            shutil.copyfile(sub_path, os.path.join(DIST_DIR, target_name))
            
    manifest_path = os.path.join(DIST_DIR, 'release_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write(f'{{"deployed_at": "{datetime.now().isoformat()}", "source_file": "{src_file}"}}\n')
        
    return True


def deploy_cloudflare(project_name=DEFAULT_CF_PROJECT, branch=DEFAULT_CF_BRANCH, log_fn=print):
    """發布至 Cloudflare Pages"""
    cmd = ['wrangler', 'pages', 'deploy', DIST_DIR, f'--project-name={project_name}', f'--branch={branch}']
    log_fn(f"[DEPLOY] 執行 Cloudflare Pages 發布: {' '.join(cmd)}")
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            log_fn(f"[DEPLOY SUCCESS] 成功發布至 Cloudflare Pages! 項目: {project_name}")
            for line in res.stdout.split('\n'):
                if 'pages.dev' in line:
                    log_fn(f"[DEPLOY URL] {line.strip()}")
            return True
        else:
            log_fn(f"[DEPLOY FAILED] Cloudflare 部署返回非零代碼:\n{res.stderr.strip() or res.stdout.strip()}")
            return False
    except FileNotFoundError:
        log_fn("[DEPLOY WARN] 未找到 wrangler。若尚未安裝，可執行: npm install -g wrangler")
        return False
    except Exception as e:
        log_fn(f"[DEPLOY EXCEPTION] Cloudflare 發布異常: {e}")
        return False


def deploy_github(repo_dir=None, branch='gh-pages', log_fn=print):
    """發布至 GitHub Pages"""
    repo_dir = repo_dir or os.environ.get('GH_PAGES_REPO', os.path.join(BASE_DIR, 'gh-pages-repo'))
    if not os.path.exists(os.path.join(repo_dir, '.git')):
        log_fn(f"[DEPLOY WARN] GitHub Pages 倉庫未找到: {repo_dir}")
        return False
        
    try:
        for item in os.listdir(DIST_DIR):
            s = os.path.join(DIST_DIR, item)
            d = os.path.join(repo_dir, item)
            if os.path.isfile(s):
                shutil.copyfile(s, d)
                
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        subprocess.run(['git', '-C', repo_dir, 'add', '.'], check=True)
        subprocess.run(['git', '-C', repo_dir, 'commit', '-m', f'Auto update dashboard: {now_str}'], check=True)
        res = subprocess.run(['git', '-C', repo_dir, 'push', 'origin', branch], capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            log_fn(f"[DEPLOY SUCCESS] 成功推送至 GitHub Pages ({branch})")
            return True
        else:
            log_fn(f"[DEPLOY FAILED] Git push 失敗: {res.stderr}")
            return False
    except Exception as e:
        log_fn(f"[DEPLOY EXCEPTION] Git 發布異常: {e}")
        return False


def auto_deploy(target=None, log_fn=print):
    """自動發布主調用函式"""
    target = target or os.environ.get('DEPLOY_TARGET', 'cloudflare').lower()
    log_fn(f"[DEPLOY] 啟動儀表板發布程序 (目標平台: {target})...")
    
    if not prepare_dist(log_fn):
        return False
        
    if target == 'cloudflare':
        return deploy_cloudflare(log_fn=log_fn)
    elif target == 'github':
        return deploy_github(log_fn=log_fn)
    elif target == 'local':
        log_fn(f"[DEPLOY] 本地發布目錄已準備完成: {DIST_DIR}")
        return True
    else:
        log_fn(f"[DEPLOY WARN] 未識別的部署目標: {target}，僅完成 dist/ 準備")
        return True


if __name__ == '__main__':
    target_arg = sys.argv[1] if len(sys.argv) > 1 else None
    auto_deploy(target=target_arg)
