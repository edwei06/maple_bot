# 相容舊啟動：把主要邏輯移到套件內，這裡只做轉呼叫
from auto_farm.app import main

if __name__ == "__main__":
    main()