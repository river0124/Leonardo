from utils import KoreaInvestEnv, KoreaInvestAPI
import yaml

def get_total_asset():
    with open("./config.yaml", encoding="UTF-8") as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)

    env_cls = KoreaInvestEnv(cfg)
    headers = env_cls.get_base_headers()
    cfg = env_cls.get_full_config()
    api = KoreaInvestAPI(cfg, headers)

    total = api.get_total_asset()
    return total

def main():
    total = get_total_asset()
    if total is None:
        print("조회 실패")
    else:
        print(f"{total}")

if __name__ == "__main__":
    main()