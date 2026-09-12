# Установка зависимостей перед запуском:
#   pip install pyautogui keyboard mss numpy opencv-python

import pyautogui
import time
import os
import keyboard
import mss
import cv2
import numpy as np
import ctypes
from ctypes import wintypes

# Папка, где лежит сам скрипт — картинки ищем рядом с ним,
# независимо от того, из какой директории запущен python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Все шаблоны теперь лежат в подпапке images/ рядом со скриптом.
# Переместите все .png файлы туда.
IMAGES_DIR = os.path.join(SCRIPT_DIR, 'images')

CLOCK_IMG = os.path.join(IMAGES_DIR, 'clock.png')
RED_SKIP_IMG = os.path.join(IMAGES_DIR, 'red_skip.png')
GREEN_START_IMG = os.path.join(IMAGES_DIR, 'green_start.png')
BLUE_BTN_IMG = os.path.join(IMAGES_DIR, 'blue_btn.png')
LEFT_ARROW_IMG = os.path.join(IMAGES_DIR, 'left_arrow.png')
RIGHT_ARROW_IMG = os.path.join(IMAGES_DIR, 'right_arrow.png')

# Шаблоны для восстановления после краша игры (окно "Перезапустить игру")
RESTART_OPTION_IMG = os.path.join(IMAGES_DIR, 'restart_option.png')
OK_BUTTON_IMG = os.path.join(IMAGES_DIR, 'ok_button.png')
GOLD_BARREL_IMG = os.path.join(IMAGES_DIR, 'gold_barrel.png')
GREEN_BOOK_IMG = os.path.join(IMAGES_DIR, 'green_book.png')
GG_ICON_IMG = os.path.join(IMAGES_DIR, 'gg_icon.png')

# Шаблоны, которые нужны на каждом проходе — сканируются ОДНИМ снимком экрана
PRIMARY_TEMPLATES = [OK_BUTTON_IMG, BLUE_BTN_IMG, RED_SKIP_IMG]
# Эти ищем вторым снимком, только если на первом нашлись красные кнопки
SECONDARY_TEMPLATES = [CLOCK_IMG, GREEN_START_IMG]

# Точка внутри области игры, где скроллим колесом мыши после восстановления.
SCROLL_X = 960
SCROLL_Y = 607

# Насколько сильно скроллить вниз (величина в "щелчках" колеса)
SCROLL_AMOUNT = 230

# Настройка точности поиска (от 0.0 до 1.0)
CONFIDENCE_LEVEL = 0.7

# Пауза между обычными кликами (сек)
CLICK_PAUSE = 0.01

# Пауза между проходами сканирования экрана (сек)
PASS_PAUSE = 0.01

# Клавиша аварийной остановки скрипта
STOP_KEY = 'esc'

# --- Область экрана для захвата (ускоряет скриншот и распознавание) ---
# Верхний левый угол: (755, 288), нижний правый угол: (1166, 926).
# Правая и нижняя границы не включаются, поэтому размер равен 411x638.
CAPTURE_REGION = {
    "left": 755,
    "top": 288,
    "width": 411,
    "height": 638,
}

# --- Периодический цикл скорости (профилактика краша GG) ---
SPEED_CYCLE_INTERVAL = 60
SPEED_DOWN_DURATION = 1
ARROW_CLICK_PAUSE = 0.3

# --- Восстановление после краша игры ---
RECOVERY_STEP_TIMEOUT = 15
RECOVERY_STEP_POLL = 0.5
POST_RESTART_DELAY = 4
GG_LONG_PRESS_DURATION = 2

# Сколько раз пересканировать экран за одну проверку (устойчивость к анимации).
SCAN_ATTEMPTS = 1
SCAN_ATTEMPT_DELAY = 0.01

# Кэш шаблонов в оттенках серого: цвет не нужен для поиска, а grayscale
# уменьшает объём данных для сопоставления в 3 раза.
_TEMPLATE_CACHE = {}

# Единственный экземпляр mss на весь скрипт — пересоздавать его на каждый кадр дорого
_sct = mss.mss()


def select_foreground_window():
    """Запоминает границы активного окна и центр для последующих действий."""
    global CAPTURE_REGION, SCROLL_X, SCROLL_Y

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("Не удалось определить активное окно после таймера.")

    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Не удалось получить границы активного окна.")

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(
            f"Активное окно имеет некорректный размер: {width}x{height}."
        )

    CAPTURE_REGION = {
        "left": rect.left,
        "top": rect.top,
        "width": width,
        "height": height,
    }
    SCROLL_X = rect.left + width // 2
    SCROLL_Y = rect.top + height // 2
    print(
        f"Выбрано активное окно: x={rect.left}, y={rect.top}, "
        f"размер={width}x{height}"
    )


def _load_template(path):
    """Загружает и кэширует шаблон сразу в формате grayscale."""
    if path not in _TEMPLATE_CACHE:
        template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise FileNotFoundError(f"Не удалось загрузить шаблон: {path}")
        _TEMPLATE_CACHE[path] = template
    return _TEMPLATE_CACHE[path]


def take_screenshot_gray():
    """
    Делает снимок экрана и сразу переводит его в grayscale.
    Если CAPTURE_REGION задан — захватывается только эта область.
    """
    monitor = CAPTURE_REGION if CAPTURE_REGION is not None else _sct.monitors[1]
    raw = _sct.grab(monitor)
    return cv2.cvtColor(np.asarray(raw), cv2.COLOR_BGRA2GRAY)


class StoppedByUser(Exception):
    """Выбрасывается, когда пользователь нажал клавишу остановки (ESC)."""
    pass


# Флаг остановки, устанавливается обработчиком нажатия клавиши (событие,
# а не опрос) — так короткое нажатие Esc не теряется между проверками.
_stop_requested = False


def _on_stop_key_pressed(event):
    global _stop_requested
    _stop_requested = True


def check_stop():
    """Проверяет, не был ли запрошен останов, и если да — прерывает скрипт."""
    if _stop_requested:
        raise StoppedByUser()


def sleep_interruptible(seconds):
    """Спит указанное время, но проверяет ESC, чтобы реагировать быстро."""
    if seconds <= 0.05:
        check_stop()
        time.sleep(seconds)
        return
    end_time = time.time() + seconds
    while time.time() < end_time:
        check_stop()
        time.sleep(0.05)


def _find_matches(screen_gray, template_gray, confidence, tolerance=20):
    """
    Ищет шаблон в grayscale-кадре. Локальные максимумы выделяются OpenCV,
    поэтому тысячи пороговых пикселей не перебираются в Python.
    """
    h, w = template_gray.shape[:2]
    if screen_gray.shape[0] < h or screen_gray.shape[1] < w:
        return []

    try:
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    except cv2.error:
        return []

    candidates_mask = result >= confidence
    if not np.any(candidates_mask):
        return []

    # Ищем один максимум в окрестности каждого совпадения.
    kernel_size = max(3, tolerance * 2 + 1)
    local_max = cv2.dilate(result, np.ones((kernel_size, kernel_size), np.uint8))
    ys, xs = np.where(candidates_mask & (result >= local_max - 1e-6))
    candidates = sorted(
        zip(xs, ys, result[ys, xs]), key=lambda candidate: -candidate[2]
    )

    points = []
    for x, y, _score in candidates:
        cx, cy = x + w // 2, y + h // 2
        if not any(
            abs(cx - px) < tolerance and abs(cy - py) < tolerance
            for px, py in points
        ):
            points.append((cx, cy))

    if CAPTURE_REGION is not None:
        points = [
            (x + CAPTURE_REGION["left"], y + CAPTURE_REGION["top"])
            for x, y in points
        ]
    return points


def scan_batch(template_paths, tolerance=20):
    """
    Делает SCAN_ATTEMPTS снимков экрана (а не один на шаблон!) и на каждом
    снимке ищет СРАЗУ ВСЕ переданные шаблоны.
    Возвращает dict {путь_к_шаблону: [(x, y), ...]}.
    """
    results = {p: [] for p in template_paths}

    for attempt in range(SCAN_ATTEMPTS):
        screen_gray = take_screenshot_gray()
        for p in template_paths:
            template = _load_template(p)
            found = _find_matches(screen_gray, template, CONFIDENCE_LEVEL, tolerance)
            for pt in found:
                if not any(abs(pt[0] - e[0]) < tolerance and abs(pt[1] - e[1]) < tolerance for e in results[p]):
                    results[p].append(pt)
        if attempt < SCAN_ATTEMPTS - 1:
            time.sleep(SCAN_ATTEMPT_DELAY)

    return results


def get_unique_targets(image_path, tolerance=20):
    """Находит все совпадения ОДНОГО шаблона на экране (обёртка над scan_batch)."""
    return scan_batch([image_path], tolerance)[image_path]


def points_near(points, ref_x, ref_y, x_tol, y_tol):
    """Фильтрует уже найденные точки — оставляет только те, что рядом со строкой (ref_x, ref_y)."""
    row_points = [(x, y) for x, y in points if abs(x - ref_x) < x_tol and abs(y - ref_y) < y_tol]
    row_points.sort(key=lambda p: abs(p[1] - ref_y))
    return row_points


def click_arrow_twice(image_path, description):
    """Находит иконку стрелки на экране и кликает по ней 2 раза подряд."""
    targets = get_unique_targets(image_path)
    if not targets:
        print(f"-> {description}: иконка не найдена на экране, пропускаем")
        return False

    x, y = targets[0]
    for i in range(2):
        check_stop()
        print(f"-> Клик по {description} ({x}, {y}) [{i + 1}/2]")
        pyautogui.click(x, y)
        sleep_interruptible(ARROW_CLICK_PAUSE)
    return True


def do_speed_cycle():
    print(f"\n--- Цикл скорости (каждые {SPEED_CYCLE_INTERVAL} сек) ---")
    ok = click_arrow_twice(LEFT_ARROW_IMG, "левая стрелка (уменьшить скорость)")
    if not ok:
        print("Цикл скорости пропущен — не нашли левую стрелку.")
        return

    sleep_interruptible(SPEED_DOWN_DURATION)

    click_arrow_twice(RIGHT_ARROW_IMG, "правая стрелка (вернуть скорость)")
    print("--- Цикл скорости завершён ---\n")


def wait_and_click_one(image_path, description, timeout=RECOVERY_STEP_TIMEOUT):
    """Ждёт появления элемента на экране до timeout секунд и кликает по нему."""
    start = time.time()
    while time.time() - start < timeout:
        check_stop()
        targets = get_unique_targets(image_path)
        if targets:
            x, y = targets[0]
            print(f"-> Найдено: {description} ({x}, {y}) — клик")
            pyautogui.click(x, y)
            sleep_interruptible(CLICK_PAUSE)
            return True
        sleep_interruptible(RECOVERY_STEP_POLL)
    print(f"-> Не дождались: {description} (таймаут {timeout} сек)")
    return False


def long_press(x, y, duration):
    """Зажимает кнопку мыши в точке (x, y) на duration секунд (эмуляция долгого тапа)."""
    pyautogui.mouseDown(x=x, y=y)
    sleep_interruptible(duration)
    pyautogui.mouseUp(x=x, y=y)


def press_gg_speed_sequence():
    """
    После восстановления после краша: сначала слегка скроллим вниз по центру
    экрана (чтобы открылись элементы управления скоростью), затем жмём
    двойную стрелку ускорения GG 2 раза подряд, и через 1 секунду —
    двойную стрелку замедления 1 раз.
    """
    print(f"-> Прокручиваем колесом мыши вниз в точке ({SCROLL_X}, {SCROLL_Y})")
    pyautogui.moveTo(SCROLL_X, SCROLL_Y)
    pyautogui.scroll(-SCROLL_AMOUNT)
    sleep_interruptible(0.3)  # даём интерфейсу время среагировать на скролл

    targets = get_unique_targets(RIGHT_ARROW_IMG)
    if not targets:
        print("-> Двойная стрелка ускорения не найдена, пропускаем")
        return

    x, y = targets[0]
    for i in range(2):
        check_stop()
        print(f"-> Клик по двойной стрелке ускорения ({x}, {y}) [{i + 1}/2]")
        pyautogui.click(x, y)
        sleep_interruptible(CLICK_PAUSE)

    sleep_interruptible(0.1)

    targets = get_unique_targets(LEFT_ARROW_IMG)
    if not targets:
        print("-> Двойная стрелка замедления не найдена, пропускаем")
        return

    x, y = targets[0]
    print(f"-> Клик по двойной стрелке замедления ({x}, {y})")
    pyautogui.click(x, y)
    sleep_interruptible(CLICK_PAUSE)


def try_crash_recovery():
    """Проверяет окно 'Перезапустить игру' и проходит цепочку восстановления, если нужно."""
    targets = get_unique_targets(RESTART_OPTION_IMG)
    if not targets:
        return False

    print("\n=== Обнаружено окно перезапуска игры — восстанавливаемся ===")

    x, y = targets[0]
    print(f"-> Клик 'Перезапустить игру' ({x}, {y})")
    pyautogui.click(x, y)
    sleep_interruptible(CLICK_PAUSE)

    wait_and_click_one(OK_BUTTON_IMG, "кнопка Ok")

    print(f"Ждём {POST_RESTART_DELAY} сек, пока игра загружается...")
    sleep_interruptible(POST_RESTART_DELAY)

    wait_and_click_one(GOLD_BARREL_IMG, "золотая бочка")
    wait_and_click_one(GREEN_BOOK_IMG, "зелёная книга")

    gg_targets = get_unique_targets(GG_ICON_IMG)
    if gg_targets:
        gx, gy = gg_targets[0]
        print(f"-> Зажимаем иконку GG на {GG_LONG_PRESS_DURATION} сек ({gx}, {gy})")
        long_press(gx, gy, GG_LONG_PRESS_DURATION)
        sleep_interruptible(CLICK_PAUSE)
    else:
        print("-> Иконка GG не найдена, пропускаем долгое нажатие")

    press_gg_speed_sequence()

    print("=== Восстановление завершено — возобновляем сбор квестов ===\n")
    return True


def run_pass():
    """
    Один проход по экрану. Сначала одним снимком проверяем Ok/синюю/красную
    кнопки — это самый частый случай. Часы и зелёную кнопку ищем вторым
    снимком, и только если на экране вообще есть красные кнопки.
    """
    check_stop()

    primary = scan_batch(PRIMARY_TEMPLATES)

    ok_buttons = primary[OK_BUTTON_IMG]
    blue_buttons = primary[BLUE_BTN_IMG]
    red_buttons = primary[RED_SKIP_IMG]

    # Шаг 0: если где-то всплыла кнопка Ok — сразу жмём её.
    for ox, oy in ok_buttons:
        check_stop()
        print(f"Найдена кнопка 'Ok' ({ox}, {oy}) — клик")
        pyautogui.click(ox, oy)
        sleep_interruptible(CLICK_PAUSE)

    # Шаг 1: забираем все готовые синие кнопки — без ожидания и без привязки к строке.
    for bx, by in blue_buttons:
        check_stop()
        print(f"Найдена готовая синяя кнопка ({bx}, {by}) — клик")
        pyautogui.click(bx, by)
        sleep_interruptible(CLICK_PAUSE)

    if not red_buttons:
        return

    red_buttons.sort(key=lambda item: item[1])
    print(f"Обнаружено квестов на экране: {len(red_buttons)}")

    # Часы и зелёную кнопку ищем только теперь, когда знаем, что есть что обрабатывать.
    secondary = scan_batch(SECONDARY_TEMPLATES)
    clocks = secondary[CLOCK_IMG]
    green_buttons = secondary[GREEN_START_IMG]

    for red_x, red_y in red_buttons:
        check_stop()

        row_clocks = points_near(clocks, red_x, red_y, x_tol=300, y_tol=70)

        if not row_clocks:
            print(f"Строка без часов (Y: {red_y}). Нажимаем 'Пропустить' ({red_x}, {red_y})")
            pyautogui.click(red_x, red_y)
            sleep_interruptible(CLICK_PAUSE)
            continue

        print(f"Найдена строка с ЧАСАМИ (Y: {red_y}).")
        row_green = points_near(green_buttons, red_x, red_y, x_tol=300, y_tol=25)
        if not row_green:
            print("-> Зелёная кнопка не найдена (квест уже запущен или уже собран). Пропускаем строку.")
            continue

        gx, gy = row_green[0]
        print(f"-> Клик на зелёную кнопку в координатах ({gx}, {gy})")
        pyautogui.click(gx, gy)
        sleep_interruptible(CLICK_PAUSE)


def scan_forever():
    """Непрерывно сканирует экран, пока пользователь не нажмёт ESC."""
    last_speed_cycle = time.time()

    while True:
        check_stop()

        if try_crash_recovery():
            sleep_interruptible(PASS_PAUSE)
            continue

        run_pass()

        if time.time() - last_speed_cycle >= SPEED_CYCLE_INTERVAL:
            do_speed_cycle()
            last_speed_cycle = time.time()

        sleep_interruptible(PASS_PAUSE)


def main():
    global _stop_requested
    _stop_requested = False
    keyboard.on_press_key(STOP_KEY, _on_stop_key_pressed)

    # Отключаем встроенные накладные расходы pyautogui:
    # FAILSAFE — проверка угла экрана перед каждым действием,
    # PAUSE — автоматическая пауза 0.1 сек ПОСЛЕ каждого вызова pyautogui.*
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0

    print("Скрипт запущен. Перейдите в окно игры. Поиск начнется через 3 секунды...")
    print(f"Нажмите {STOP_KEY.upper()} в любой момент, чтобы остановить скрипт.")
    sleep_interruptible(3)

    # Прогружаем все шаблоны в память сразу, чтобы первый проход тоже был быстрым
    all_templates = set(PRIMARY_TEMPLATES + SECONDARY_TEMPLATES + [
        LEFT_ARROW_IMG, RIGHT_ARROW_IMG, RESTART_OPTION_IMG,
        OK_BUTTON_IMG, GOLD_BARREL_IMG, GREEN_BOOK_IMG, GG_ICON_IMG
    ])
    for path in all_templates:
        try:
            _load_template(path)
        except Exception as e:
            print(f"Предупреждение: не удалось загрузить шаблон {path}: {e}")

    try:
        scan_forever()
    except StoppedByUser:
        print("Остановлено пользователем (ESC). Скрипт завершён.")


if __name__ == "__main__":
    main()