import pyautogui
import time
import os
import keyboard

# Папка, где лежит сам скрипт — картинки ищем рядом с ним,
# независимо от того, из какой директории запущен python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Имена файлов-шаблонов (полный путь, чтобы работало из любой рабочей директории)
CLOCK_IMG = os.path.join(SCRIPT_DIR, 'clock.png')
RED_SKIP_IMG = os.path.join(SCRIPT_DIR, 'red_skip.png')
GREEN_START_IMG = os.path.join(SCRIPT_DIR, 'green_start.png')
BLUE_BTN_IMG = os.path.join(SCRIPT_DIR, 'blue_btn.png')
LEFT_ARROW_IMG = os.path.join(SCRIPT_DIR, 'left_arrow.png')
RIGHT_ARROW_IMG = os.path.join(SCRIPT_DIR, 'right_arrow.png')

# Шаблоны для восстановления после краша игры (окно "Перезапустить игру")
RESTART_OPTION_IMG = os.path.join(SCRIPT_DIR, 'restart_option.png')
OK_BUTTON_IMG = os.path.join(SCRIPT_DIR, 'ok_button.png')
GOLD_BARREL_IMG = os.path.join(SCRIPT_DIR, 'gold_barrel.png')
GREEN_BOOK_IMG = os.path.join(SCRIPT_DIR, 'green_book.png')
GG_ICON_IMG = os.path.join(SCRIPT_DIR, 'gg_icon.png')

# Настройка точности поиска (от 0.0 до 1.0)
CONFIDENCE_LEVEL = 0.7

# Пауза между обычными кликами (сек)
CLICK_PAUSE = 0.1

# Пауза между проходами сканирования экрана (сек)
PASS_PAUSE = 0.3

# Клавиша аварийной остановки скрипта
STOP_KEY = 'esc'

# --- Периодический цикл скорости (профилактика краша GG) ---
# Раз в SPEED_CYCLE_INTERVAL секунд скрипт нажимает левую стрелку (уменьшить
# скорость) 2 раза, ждёт SPEED_DOWN_DURATION секунд, затем нажимает правую
# стрелку (увеличить скорость обратно) тоже 2 раза.
SPEED_CYCLE_INTERVAL = 30
SPEED_DOWN_DURATION = 5
ARROW_CLICK_PAUSE = 0.3

# --- Восстановление после краша игры ---
RECOVERY_STEP_TIMEOUT = 15     # сколько ждать появления каждого элемента цепочки (сек)
RECOVERY_STEP_POLL = 0.5       # с какой частотой проверять экран во время ожидания
POST_RESTART_DELAY = 4         # ожидание загрузки игры после нажатия Ok (сек)
GG_LONG_PRESS_DURATION = 2     # сколько секунд удерживать иконку GG

# Сколько раз пересканировать экран за одну проверку, чтобы не терять
# кнопки из-за анимации/эффектов, которые могут "смазать" один конкретный кадр.
# Уменьшено с 3 до 2 для скорости — при новых проблемах можно вернуть к 3.
SCAN_ATTEMPTS = 2
SCAN_ATTEMPT_DELAY = 0.1


class StoppedByUser(Exception):
    """Выбрасывается, когда пользователь нажал клавишу остановки (ESC)."""
    pass


def check_stop():
    """Проверяет, не нажата ли клавиша остановки, и если да — прерывает скрипт."""
    if keyboard.is_pressed(STOP_KEY):
        raise StoppedByUser()


def sleep_interruptible(seconds):
    """Спит указанное время, но проверяет ESC каждые 0.1 сек, чтобы реагировать мгновенно."""
    end_time = time.time() + seconds
    while time.time() < end_time:
        check_stop()
        time.sleep(0.1)


def get_unique_targets(image_path, tolerance=20):
    """
    Находит все совпадения на экране и удаляет дубликаты координат-соседей.
    Делает несколько быстрых попыток подряд и объединяет результаты —
    если анимация "смазала" кнопку на одном кадре, она может поймать её на другом.
    """
    unique_points = []

    for attempt in range(SCAN_ATTEMPTS):
        try:
            matches = list(pyautogui.locateAllOnScreen(image_path, confidence=CONFIDENCE_LEVEL))
        except Exception:
            matches = []

        for m in matches:
            center = pyautogui.center(m)
            if not any(abs(center.x - u[0]) < tolerance and abs(center.y - u[1]) < tolerance for u in unique_points):
                unique_points.append((center.x, center.y))

        if attempt < SCAN_ATTEMPTS - 1:
            time.sleep(SCAN_ATTEMPT_DELAY)

    return unique_points


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
    """
    Раз в SPEED_CYCLE_INTERVAL секунд: снижаем скорость (левая стрелка x2),
    ждём SPEED_DOWN_DURATION секунд, возвращаем скорость обратно (правая стрелка x2).
    Это профилактика — периодическая просадка скорости, чтобы игра не крашилась
    от постоянной работы на завышенном множителе.
    """
    print(f"\n--- Цикл скорости (каждые {SPEED_CYCLE_INTERVAL} сек) ---")
    ok = click_arrow_twice(LEFT_ARROW_IMG, "левая стрелка (уменьшить скорость)")
    if not ok:
        print("Цикл скорости пропущен — не нашли левую стрелку.")
        return

    sleep_interruptible(SPEED_DOWN_DURATION)

    click_arrow_twice(RIGHT_ARROW_IMG, "правая стрелка (вернуть скорость)")
    print("--- Цикл скорости завершён ---\n")


def wait_and_click_one(image_path, description, timeout=RECOVERY_STEP_TIMEOUT):
    """Ждёт появления элемента на экране до timeout секунд и кликает по нему. Возвращает True/False."""
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


def try_crash_recovery():
    """
    Проверяет, не появилось ли окно 'Перезапустить игру' (последствие краша GG),
    и если да — проходит всю цепочку восстановления:
    Перезапустить игру -> Ok -> золотая бочка -> зелёная книга ->
    долгое нажатие на GG -> двойная стрелка.
    Возвращает True, если восстановление запускалось (чтобы вызывающий код
    пропустил обычный проход квестов в этой итерации и начал заново).
    """
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

    wait_and_click_one(RIGHT_ARROW_IMG, "двойная стрелка")

    print("=== Восстановление завершено — возобновляем сбор квестов ===\n")
    return True


def claim_all_ready_blue_buttons():
    """
    Каждый проход ищет ВСЕ синие кнопки на экране (без привязки к конкретной строке)
    и сразу кликает по ним. Никакого ожидания — просто забираем то, что уже готово.
    """
    blue_buttons = get_unique_targets(BLUE_BTN_IMG)
    for bx, by in blue_buttons:
        check_stop()
        print(f"Найдена готовая синяя кнопка ({bx}, {by}) — клик")
        pyautogui.click(bx, by)
        sleep_interruptible(CLICK_PAUSE)
    return len(blue_buttons)


def run_pass():
    """Один проход по экрану: сначала забираем готовые награды, потом обрабатываем квесты."""
    check_stop()

    # Шаг 1: всегда сначала проверяем и забираем ВСЕ готовые синие кнопки,
    # независимо от того, к какой строке они относятся — без ожидания.
    claim_all_ready_blue_buttons()

    check_stop()
    red_buttons = get_unique_targets(RED_SKIP_IMG)

    if not red_buttons:
        print("Не найдено ни одной красной кнопки.")
        return

    red_buttons.sort(key=lambda item: item[1])
    print(f"Обнаружено квестов на экране: {len(red_buttons)}")

    # Сканируем часы и зелёные кнопки ОДИН раз на весь проход,
    # а не заново для каждой строки — это главный источник ускорения.
    clocks = get_unique_targets(CLOCK_IMG)
    green_buttons = get_unique_targets(GREEN_START_IMG)

    for red_x, red_y in red_buttons:
        check_stop()

        row_clocks = points_near(clocks, red_x, red_y, x_tol=300, y_tol=70)

        if not row_clocks:
            # Часов нет — жмём красную «Пропустить»
            print(f"Строка без часов (Y: {red_y}). Нажимаем 'Пропустить' ({red_x}, {red_y})")
            pyautogui.click(red_x, red_y)
            sleep_interruptible(CLICK_PAUSE)
            continue

        # Часы есть — жмём зелёную «Начать» и идём дальше, НЕ дожидаясь результата.
        # Синяя кнопка для этого квеста будет подхвачена автоматически
        # на одном из следующих проходов через claim_all_ready_blue_buttons().
        print(f"Найдена строка с ЧАСАМИ (Y: {red_y}).")
        row_green = points_near(green_buttons, red_x, red_y, x_tol=300, y_tol=25)
        if not row_green:
            print("-> Зелёная кнопка не найдена (квест уже запущен или уже собран). Пропускаем строку.")
            continue

        gx, gy = row_green[0]
        print(f"-> Клик на зелёную кнопку в координатах ({gx}, {gy})")
        pyautogui.click(gx, gy)
        sleep_interruptible(CLICK_PAUSE)


def main():
    print("Скрипт запущен. Перейдите в окно игры. Поиск начнется через 3 секунды...")
    print(f"Нажмите {STOP_KEY.upper()} в любой момент, чтобы остановить скрипт.")
    time.sleep(3)

    last_speed_cycle = time.time()

    try:
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
    except StoppedByUser:
        print("Остановлено пользователем (ESC). Скрипт завершён.")


if __name__ == "__main__":
    main()
