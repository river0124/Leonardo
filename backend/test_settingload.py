# test_settings_manager.py

from settings_manager import save_settings, load_settings

# 테스트용 설정 딕셔너리
test_config = {
    "atr_period": 17,
    "max_loss_ratio": -0.02,
    "test_key": "test_value"
}

print("✅ save_settings() 테스트 중...")
save_settings(test_config)

print("\n✅ load_settings() 테스트 중...")
loaded_config = load_settings()

print("\n📦 불러온 설정 내용:")
for k, v in loaded_config.items():
    print(f"{k}: {v}")