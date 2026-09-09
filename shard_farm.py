import pyautogui
import keyboard
import time
import os
import cv2
import numpy as np
from PIL import Image

# Папка, где лежит сам скрипт — картинки ищем рядом с ним
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANCHOR_IMG = os.path.join(SCRIPT_DIR, 'captcha_anchor.png')

# --- Настройки дабл-клика ---
POINT_1 = (770, 240)
POINT_2 = (900, 240)
STOP_KEY = 'esc'

# --- Настройки капчи ---
CONFIDENCE_LEVEL = 0.8
CLICK_PAUSE = 0.15

# Смещения (в пикселях) относительно левого верхнего угла найденного якоря
# (текст "Выберите все ячейки с такой бочкой"). Пересчитаны под реальный экран.
ICON_OFFSET = (470, 14)
GRID_COL_OFFSETS = [111, 248, 385]
GRID_ROW_OFFSETS = [115, 252, 389]
BUTTON_OFFSET = (248, 520)

CELL_HALF_SIZE = 55
ICON_HALF_SIZE = 25
MATCH_THRESHOLD_RATIO = 0.85
DEBUG_SAVE_CROPS = False

# Раз в сколько циклов дабл-клика проверять, не появилась ли капча.
# Каждая проверка — это скриншот + поиск по экрану, поэтому слишком маленькое
# значение будет заметно тормозить дабл-клик. Подбирай под свои нужды.
CAPTCHA_CHECK_INTERVAL = 50

# Убираем встроенную паузу pyautogui после каждого действия — основной источник задержки.
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True  # не трогаем — угол экрана как аварийный стоп


class StoppedByUser(Exception):
    pass


def check_stop():
    if keyboard.is_pressed(STOP_KEY):
        raise StoppedByUser()


def sleep_interruptible(seconds):
    end_time = time.time() + seconds
    while time.time() < end_time:
        check_stop()
        time.sleep(0.05)


def double_click(x, y):
    """Двойной клик одним вызовом, без паузы между двумя нажатиями (interval=0)."""
    pyautogui.click(x, y, clicks=2, interval=0)


# ---------------- Решение капчи ----------------

def find_anchor():
    try:
        return pyautogui.locateOnScreen(ANCHOR_IMG, confidence=CONFIDENCE_LEVEL)
    except Exception:
        return None


def crop_region(screenshot, cx, cy, half):
    left = max(cx - half, 0)
    top = max(cy - half, 0)
    right = min(cx + half, screenshot.width)
    bottom = min(cy + half, screenshot.height)
    return screenshot.crop((left, top, right, bottom))


def hsv_histogram(pil_image):
    img = cv2.cvtColor(np.array(pil_image.convert('RGB')), cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([img], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def similarity(hist_a, hist_b):
    return cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)


def solve_captcha(box):
    print("\n=== Обнаружена анти-макро капча — решаем ===")
    anchor_x, anchor_y = box.left, box.top
    screenshot = pyautogui.screenshot()

    if DEBUG_SAVE_CROPS:
        debug_dir = os.path.join(SCRIPT_DIR, 'debug_captcha')
        os.makedirs(debug_dir, exist_ok=True)

    icon_cx = anchor_x + ICON_OFFSET[0]
    icon_cy = anchor_y + ICON_OFFSET[1]
    ref_crop = crop_region(screenshot, icon_cx, icon_cy, ICON_HALF_SIZE)
    ref_hist = hsv_histogram(ref_crop)
    if DEBUG_SAVE_CROPS:
        ref_crop.save(os.path.join(debug_dir, 'reference.png'))

    cell_positions = []
    scores = []
    idx = 0
    for row_off in GRID_ROW_OFFSETS:
        for col_off in GRID_COL_OFFSETS:
            idx += 1
            cx = anchor_x + col_off
            cy = anchor_y + row_off
            cell_crop = crop_region(screenshot, cx, cy, CELL_HALF_SIZE)
            cell_hist = hsv_histogram(cell_crop)
            score = similarity(ref_hist, cell_hist)
            cell_positions.append((cx, cy))
            scores.append(score)
            if DEBUG_SAVE_CROPS:
                cell_crop.save(os.path.join(debug_dir, f'cell_{idx}.png'))

    best = max(scores)
    threshold = best * MATCH_THRESHOLD_RATIO
    matched = [pos for pos, sc in zip(cell_positions, scores) if sc >= threshold]

    print(f"Совпало ячеек: {len(matched)} (лучшая схожесть {best:.3f})")

    for (x, y) in matched:
        check_stop()
        print(f"-> Клик по совпавшей ячейке ({x}, {y})")
        pyautogui.click(x, y)
        sleep_interruptible(CLICK_PAUSE)

    btn_x = anchor_x + BUTTON_OFFSET[0]
    btn_y = anchor_y + BUTTON_OFFSET[1]
    print(f"-> Клик по кнопке подтверждения ({btn_x}, {btn_y})")
    pyautogui.click(btn_x, btn_y)
    sleep_interruptible(CLICK_PAUSE)

    print("=== Капча решена — возобновляем дабл-клики ===\n")


# ---------------- Основной цикл ----------------

def main():
    print(f"Скрипт запущен. Дабл-клик по {POINT_1} и {POINT_2} на максимальной скорости.")
    print(f"Каждые {CAPTCHA_CHECK_INTERVAL} циклов проверяется анти-макро капча.")
    print(f"Нажми {STOP_KEY.upper()} в любой момент, чтобы остановить.")
    print("Начало через 3 секунды...")
    time.sleep(3)

    count = 0
    try:
        while True:
            check_stop()

            # Раз в CAPTCHA_CHECK_INTERVAL циклов проверяем, не всплыла ли капча
            if count % CAPTCHA_CHECK_INTERVAL == 0:
                box = find_anchor()
                if box:
                    solve_captcha(box)

            double_click(*POINT_1)
            double_click(*POINT_2)
            count += 1

    except StoppedByUser:
        print(f"\nОстановлено пользователем (ESC). Циклов выполнено: {count}")
    except KeyboardInterrupt:
        print(f"\nОстановлено (Ctrl+C). Циклов выполнено: {count}")


if __name__ == "__main__":
    main()