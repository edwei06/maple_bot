import os
import json
import time
import ctypes
from typing import Dict, Tuple

# 依賴：pip install mss opencv-python
import mss
import cv2
import numpy as np

# =========== 停止鍵(F12) ===========
VK_F12 = 0x7B
user32 = ctypes.windll.user32

def is_stop_pressed() -> bool:
    try:
        state = user32.GetAsyncKeyState(VK_F12)
        return bool(state & 0x8000)
    except Exception:
        return False


# =========== 範本比對器 ===========
class TemplateDetector:
    """
    用 cv2.TM_CCOEFF_NORMED 對 ROI 做 win/loss/draw 範本比對。
    會回傳每一個範本的 (score, loc)，以及最佳標籤與分數。
    """
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = templates_dir
        self.templates = {}
        self.load_templates()

    def load_templates(self):
        needed = ["win", "loss", "draw"]
        tpls = {}
        for name in needed:
            path = os.path.join(self.templates_dir, f"{name}.png")
            if not os.path.exists(path):
                raise FileNotFoundError(f"找不到範本：{path}")
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise RuntimeError(f"無法讀取範本：{path}")
            tpls[name] = img
        self.templates = tpls

    def match_all(self, gray_roi: np.ndarray) -> Tuple[Dict[str, Tuple[float, Tuple[int, int]]], str, float]:
        """
        回傳:
          scores: {label: (max_score, max_loc)}
          best_label: str
          best_score: float
        """
        scores = {}
        best_label, best_score = "", -1.0
        for label, tpl in self.templates.items():
            h, w = tpl.shape[:2]
            H, W = gray_roi.shape[:2]
            if H < h or W < w:
                # 範本比 ROI 大，略過
                scores[label] = (-1.0, (0, 0))
                continue
            res = cv2.matchTemplate(gray_roi, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            scores[label] = (float(max_val), (int(max_loc[0]), int(max_loc[1])))
            if max_val > best_score:
                best_score = float(max_val)
                best_label = label
        return scores, best_label, best_score


# =========== ROI 選取器（滑鼠拖曳） ===========
class ROISelector:
    """
    在顯示畫面上用滑鼠左鍵拖曳選取矩形 ROI。
    """
    def __init__(self):
        self.dragging = False
        self.start = (0, 0)
        self.end = (0, 0)
        self.rect = None  # (x, y, w, h)

    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.dragging = True
            self.start = (x, y)
            self.end = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging:
            self.end = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = False
            self.end = (x, y)
            x1, y1 = self.start
            x2, y2 = self.end
            x_min, y_min = min(x1, x2), min(y1, y2)
            x_max, y_max = max(x1, x2), max(y1, y2)
            w = max(0, x_max - x_min)
            h = max(0, y_max - y_min)
            if w >= 5 and h >= 5:
                self.rect = (x_min, y_min, w, h)

    def get(self):
        return self.rect

    def clear(self):
        self.rect = None
        self.dragging = False


# =========== 文字/框線 UI ===========
def draw_text(canvas, text, org, scale=0.6, color=(255,255,255), thickness=1, bg=(0,0,0)):
    """
    畫有底色的文字，避免不同背景下看不清。
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    x, y = org
    cv2.rectangle(canvas, (x-3, y-th-3), (x+tw+3, y+baseline+3), bg, -1)
    cv2.putText(canvas, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)

def clamp_roi_to_monitor(rect, mon_w, mon_h):
    if rect is None:
        return None
    x, y, w, h = rect
    x = max(0, min(x, mon_w-1))
    y = max(0, min(y, mon_h-1))
    w = max(1, min(w, mon_w - x))
    h = max(1, min(h, mon_h - y))
    return (x, y, w, h)


# =========== 主流程 ===========
def main():
    # 視窗與滑桿
    win_name = "ROI Calibrator (拖曳左鍵選 ROI，S=儲存，C=清除，M=切螢幕，R=重載範本，F12/ESC/Q=離開)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 1200, 700)

    # 門檻滑桿（0~100 -> 0.00~1.00）
    def _nothing(x): pass
    cv2.createTrackbar("threshold x100", win_name, 85, 100, _nothing)

    selector = ROISelector()
    cv2.setMouseCallback(win_name, selector.on_mouse)

    # 多螢幕支援
    sct = mss.mss()
    monitor_index = 1  # 預設第 1 個實體螢幕
    num_monitors = max(1, len(sct.monitors) - 1)

    # 載入範本
    try:
        detector = TemplateDetector(templates_dir="templates")
    except Exception as e:
        print(f"[錯誤] 無法載入範本：{e}")
        print("請確認 templates/win.png, templates/loss.png, templates/draw.png 存在且可讀。")
        return

    # ROI 預設（如果 roi.json 存在，就自動載入）
    roi_json_path = "roi.json"
    roi_rect = None
    if os.path.exists(roi_json_path):
        try:
            with open(roi_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                roi_rect = (int(data["left"]), int(data["top"]), int(data["width"]), int(data["height"]))
                print(f"[資訊] 已載入 roi.json：{roi_rect}")
        except Exception as e:
            print(f"[警告] 讀取 roi.json 失敗：{e}")

    last_best_label = ""
    fps_t0 = time.time()
    fps_counter = 0
    fps = 0.0

    while True:
        if is_stop_pressed():
            break

        # 取得目前螢幕畫面
        mon = sct.monitors[monitor_index] if monitor_index < len(sct.monitors) else sct.monitors[1]
        left, top, width, height = mon["left"], mon["top"], mon["width"], mon["height"]
        frame_bgra = np.array(sct.grab(mon))  # BGRA
        frame = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)
        overlay = frame.copy()

        # 門檻
        th_x100 = cv2.getTrackbarPos("threshold x100", win_name)
        threshold = max(0, min(th_x100, 100)) / 100.0

        # 畫面中座標是相對於該 monitor 的 (0,0)。抓 ROI 畫面並比對。
        # ROI 來源優先：滑鼠新選的 > 已載入 roi.json
        rect = selector.get() or roi_rect
        rect = clamp_roi_to_monitor(rect, width, height)

        best_label = ""
        best_score = -1.0
        scores = { "win": (-1.0, (0,0)), "loss": (-1.0, (0,0)), "draw": (-1.0, (0,0)) }

        if rect is not None and rect[2] >= 5 and rect[3] >= 5:
            x, y, w, h = rect
            roi_gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
            try:
                scores, best_label, best_score = detector.match_all(roi_gray)
                # 在 ROI 上畫出最佳匹配位置的框
                if best_label and best_score >= 0:
                    tpl = detector.templates[best_label]
                    th, tw = tpl.shape[:2]
                    _, (mx, my) = scores[best_label]
                    cv2.rectangle(overlay, (x+mx, y+my), (x+mx+tw, y+my+th), (0, 255, 255), 2)
            except Exception as e:
                draw_text(overlay, f"[比對錯誤] {str(e)}", (10, 30), bg=(0,0,255))

            # 畫 ROI 框
            cv2.rectangle(overlay, (x, y), (x+w, y+h), (0, 200, 255), 2)
            draw_text(overlay, f"ROI: x={x} y={y} w={w} h={h}", (10, 30))
        else:
            draw_text(overlay, "請用滑鼠左鍵拖曳畫出 ROI", (10, 30))

        # 顯示分數與判定（左上角）
        y_cursor = 60
        for name in ["win", "loss", "draw"]:
            sc = scores.get(name, (-1.0, (0,0)))[0]
            draw_text(overlay, f"{name.upper():<4}: {sc:6.3f}", (10, y_cursor))
            y_cursor += 24

        passed = (best_score >= threshold)
        draw_text(
            overlay,
            f"BEST: {best_label or '-'}  score={best_score:6.3f}  threshold={threshold:.2f}  -> {'PASS' if passed else 'FAIL'}",
            (10, y_cursor)
        )
        y_cursor += 24

        # FPS
        fps_counter += 1
        now = time.time()
        if now - fps_t0 >= 0.5:
            fps = fps_counter / (now - fps_t0)
            fps_counter = 0
            fps_t0 = now
        draw_text(overlay, f"FPS: {fps:.1f} | 螢幕: {monitor_index}/{num_monitors}", (10, y_cursor))

        # 即時顯示
        cv2.imshow(win_name, overlay)

        # 事件處理
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord('q')) or is_stop_pressed():  # ESC or 'q' or F12
            break
        elif key == ord('s'):
            # 儲存 ROI
            rect_to_save = selector.get() or roi_rect
            if rect_to_save is None:
                print("[提示] 尚未選擇 ROI，無法儲存。")
            else:
                x, y, w, h = rect_to_save
                data = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
                with open(roi_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"[已儲存] roi.json: {data}")
                # 固定 ROI（把滑鼠選取轉成持久 ROI）
                roi_rect = (x, y, w, h)
                selector.clear()
        elif key == ord('c'):
            selector.clear()
            roi_rect = None
            print("[動作] 已清除 ROI")
        elif key == ord('m'):
            # 切換實體螢幕
            if num_monitors > 1:
                monitor_index += 1
                if monitor_index > num_monitors:
                    monitor_index = 1
                selector.clear()
                roi_rect = None
                print(f"[動作] 切換到螢幕 #{monitor_index}")
            else:
                print("[提示] 僅有單一螢幕")
        elif key == ord('r'):
            try:
                detector.load_templates()
                print("[動作] 已重新載入範本")
            except Exception as e:
                print(f"[錯誤] 重新載入範本失敗：{e}")

    cv2.destroyAllWindows()
    sct.close()
    print("結束校準。")


if __name__ == "__main__":
    main()
