#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>

#define MAX_LANES 32
#define CONFIG_FILE "settings.json"
#define SCREENSHOT_FILE "Screenshot.bmp"

typedef struct {
    char name[32];
    int x;
    char key_str[16];
    WORD vk;
    int threshold;
    bool is_pressed;
} Lane;

typedef struct {
    int bbox_left;
    int bbox_top;
    int bbox_right;
    int bbox_bottom;
    int judgement_line;
    int global_threshold;
    int input_delay_ms;
    int skill_level;
    double misread_chance;   // percent chance (0-100) that a note press is misread
    double misread_ms;       // lane ignores input for this many ms after a misread
    double stamina_max;      // max clicks in stamina pool (0 = disabled)
    double stamina_regen;    // stamina regenerated per 20 ms
    double strain_step_pct;    // every X% stamina lost (0 = disabled)
    double strain_misread_pct; // misread chance increases by y%
    double strain_skill_ms;    // skill delay increases by z ms
    double strain_regen_pct;   // stamina regen decreased by Z%
    char input_mode[16]; // "hold" or "tap"
    Lane lanes[MAX_LANES];
    int lane_count;
} AppConfig;

typedef struct {
    HDC hScreenDC;
    HDC hMemDC;
    HBITMAP hBitmap;
    HBITMAP hOldBitmap;
    void* pBits;
    int width;
    int height;
} CaptureContext;

// Global state
static AppConfig g_config;
static bool g_is_running = false;
static bool g_program_active = true;

// Helper to convert character / string to Virtual Key code
WORD resolve_vk(const char* key_str) {
    if (!key_str || strlen(key_str) == 0) return 0;
    if (_stricmp(key_str, "space") == 0) return VK_SPACE;
    if (_stricmp(key_str, "left") == 0) return VK_LEFT;
    if (_stricmp(key_str, "right") == 0) return VK_RIGHT;
    if (_stricmp(key_str, "up") == 0) return VK_UP;
    if (_stricmp(key_str, "down") == 0) return VK_DOWN;
    if (_stricmp(key_str, "shift") == 0) return VK_SHIFT;
    if (_stricmp(key_str, "ctrl") == 0) return VK_CONTROL;
    if (_stricmp(key_str, "enter") == 0) return VK_RETURN;
    if (_stricmp(key_str, "tab") == 0) return VK_TAB;

    SHORT res = VkKeyScanA(key_str[0]);
    if (res == -1) return (WORD)key_str[0];
    return LOBYTE(res);
}

void set_default_config(AppConfig* cfg) {
    cfg->bbox_left = 644;
    cfg->bbox_top = 760;
    cfg->bbox_right = 1269;
    cfg->bbox_bottom = 761;
    cfg->judgement_line = 0;
    cfg->global_threshold = 30;
    cfg->input_delay_ms = 0;
    cfg->skill_level = 0;
    cfg->misread_chance = 0;
    cfg->misread_ms = 0;
    cfg->stamina_max = 0;
    cfg->stamina_regen = 0.0;
    cfg->strain_step_pct = 0;
    cfg->strain_misread_pct = 0;
    cfg->strain_skill_ms = 0;
    cfg->strain_regen_pct = 0;
    strcpy(cfg->input_mode, "hold");

    cfg->lane_count = 4;
    strcpy(cfg->lanes[0].name, "Lane 1");
    cfg->lanes[0].x = 10;
    strcpy(cfg->lanes[0].key_str, "q");
    cfg->lanes[0].vk = resolve_vk("q");
    cfg->lanes[0].threshold = 30;
    cfg->lanes[0].is_pressed = false;

    strcpy(cfg->lanes[1].name, "Lane 2");
    cfg->lanes[1].x = 180;
    strcpy(cfg->lanes[1].key_str, "w");
    cfg->lanes[1].vk = resolve_vk("w");
    cfg->lanes[1].threshold = 30;
    cfg->lanes[1].is_pressed = false;

    strcpy(cfg->lanes[2].name, "Lane 3");
    cfg->lanes[2].x = 340;
    strcpy(cfg->lanes[2].key_str, "[");
    cfg->lanes[2].vk = resolve_vk("[");
    cfg->lanes[2].threshold = 30;
    cfg->lanes[2].is_pressed = false;

    strcpy(cfg->lanes[3].name, "Lane 4");
    cfg->lanes[3].x = 500;
    strcpy(cfg->lanes[3].key_str, "]");
    cfg->lanes[3].vk = resolve_vk("]");
    cfg->lanes[3].threshold = 30;
    cfg->lanes[3].is_pressed = false;
}

// Reads a numeric value for "key" from a JSON buffer. Returns true on success.
static bool json_get_number(const char* buf, const char* key, double* out) {
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char* p = strstr(buf, needle);
    if (!p) return false;
    p += strlen(needle);
    while (*p == ' ' || *p == '\t') p++;
    if (*p != ':') return false;
    p++;
    char* endp = NULL;
    double v = strtod(p, &endp);
    if (endp == p) return false;
    *out = v;
    return true;
}

// Simple JSON config loader
bool load_config_file(AppConfig* cfg, const char* filename) {
    FILE* f = fopen(filename, "r");
    if (!f) return false;

    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (len <= 0) { fclose(f); return false; }
    char* buf = (char*)malloc(len + 1);
    if (!buf) { fclose(f); return false; }
    fread(buf, 1, len, f);
    buf[len] = '\0';
    fclose(f);

    // Parse bbox: [644, 760, 1269, 761]
    char* pBbox = strstr(buf, "\"bbox\"");
    if (pBbox) {
        int l, t, r, b;
        if (sscanf(pBbox, "\"bbox\": [%d, %d, %d, %d]", &l, &t, &r, &b) == 4 ||
            sscanf(pBbox, "\"bbox\":[%d,%d,%d,%d]", &l, &t, &r, &b) == 4 ||
            sscanf(pBbox, "\"bbox\": [ %d , %d , %d , %d ]", &l, &t, &r, &b) == 4) {
            cfg->bbox_left = l;
            cfg->bbox_top = t;
            cfg->bbox_right = r;
            cfg->bbox_bottom = b;
        }
    }

    char* pThresh = strstr(buf, "\"global_threshold\"");
    if (pThresh) {
        int val = 0;
        if (sscanf(pThresh, "\"global_threshold\": %d", &val) == 1 ||
            sscanf(pThresh, "\"global_threshold\":%d", &val) == 1) {
            cfg->global_threshold = val;
        }
    }

    char* pDelay = strstr(buf, "\"input_delay_ms\"");
    if (!pDelay) pDelay = strstr(buf, "\"delay_ms\"");
    if (pDelay) {
        int dval = 0;
        if (sscanf(pDelay, "\"input_delay_ms\": %d", &dval) == 1 ||
            sscanf(pDelay, "\"input_delay_ms\":%d", &dval) == 1 ||
            sscanf(pDelay, "\"delay_ms\": %d", &dval) == 1 ||
            sscanf(pDelay, "\"delay_ms\":%d", &dval) == 1) {
            cfg->input_delay_ms = dval;
        }
    }

    char* pSkill = strstr(buf, "\"skill_level\"");
    if (!pSkill) pSkill = strstr(buf, "\"skill_level_ms\"");
    if (!pSkill) pSkill = strstr(buf, "\"input_variance_ms\"");
    if (pSkill) {
        int sval = 0;
        if (sscanf(pSkill, "\"skill_level\": %d", &sval) == 1 ||
            sscanf(pSkill, "\"skill_level\":%d", &sval) == 1 ||
            sscanf(pSkill, "\"skill_level_ms\": %d", &sval) == 1 ||
            sscanf(pSkill, "\"skill_level_ms\":%d", &sval) == 1 ||
            sscanf(pSkill, "\"input_variance_ms\": %d", &sval) == 1 ||
            sscanf(pSkill, "\"input_variance_ms\":%d", &sval) == 1) {
            cfg->skill_level = sval;
        }
    }

    {
        double dv = 0.0;
        if (json_get_number(buf, "misread_chance", &dv)) {
            cfg->misread_chance = dv < 0.0 ? 0.0 : (dv > 100.0 ? 100.0 : dv);
        }
        if (json_get_number(buf, "misread_ms", &dv)) {
            cfg->misread_ms = dv < 0.0 ? 0.0 : dv;
        }
        if (json_get_number(buf, "stamina_max", &dv)) {
            cfg->stamina_max = dv < 0.0 ? 0.0 : dv;
        }
        if (json_get_number(buf, "stamina_regen", &dv)) {
            cfg->stamina_regen = dv < 0.0 ? 0.0 : dv;
        }
        if (json_get_number(buf, "strain_step_pct", &dv)) {
            cfg->strain_step_pct = dv < 0.0 ? 0.0 : (dv > 100.0 ? 100.0 : dv);
        }
        if (json_get_number(buf, "strain_misread_pct", &dv)) {
            cfg->strain_misread_pct = dv < 0.0 ? 0.0 : (dv > 100.0 ? 100.0 : dv);
        }
        if (json_get_number(buf, "strain_skill_ms", &dv)) {
            cfg->strain_skill_ms = dv < 0.0 ? 0.0 : dv;
        }
        if (json_get_number(buf, "strain_regen_pct", &dv)) {
            cfg->strain_regen_pct = dv < 0.0 ? 0.0 : (dv > 100.0 ? 100.0 : dv);
        }
    }

    char* pMode = strstr(buf, "\"input_mode\"");
    if (pMode) {
        char m[16] = {0};
        if (sscanf(pMode, "\"input_mode\": \"%15[^\"]\"", m) == 1) {
            strcpy(cfg->input_mode, m);
        }
    }

    // Parse lanes
    char* pLanes = strstr(buf, "\"lanes\"");
    if (pLanes) {
        cfg->lane_count = 0;
        char* cur = pLanes;
        while ((cur = strchr(cur, '{')) != NULL && cfg->lane_count < MAX_LANES) {
            char* end = strchr(cur, '}');
            if (!end) break;

            int lane_x = 0;
            int lane_th = cfg->global_threshold;
            char lane_key[16] = "";
            char lane_name[32] = "";

            char* px = strstr(cur, "\"x\"");
            if (px && px < end) sscanf(px, "\"x\": %d", &lane_x);

            char* pk = strstr(cur, "\"key\"");
            if (pk && pk < end) sscanf(pk, "\"key\": \"%15[^\"]\"", lane_key);

            char* pn = strstr(cur, "\"name\"");
            if (pn && pn < end) sscanf(pn, "\"name\": \"%31[^\"]\"", lane_name);

            char* pt = strstr(cur, "\"threshold\"");
            if (pt && pt < end) sscanf(pt, "\"threshold\": %d", &lane_th);

            if (strlen(lane_key) > 0) {
                int i = cfg->lane_count;
                if (strlen(lane_name) > 0) strcpy(cfg->lanes[i].name, lane_name);
                else sprintf(cfg->lanes[i].name, "Lane %d", i + 1);

                cfg->lanes[i].x = lane_x;
                strcpy(cfg->lanes[i].key_str, lane_key);
                cfg->lanes[i].vk = resolve_vk(lane_key);
                cfg->lanes[i].threshold = lane_th;
                cfg->lanes[i].is_pressed = false;
                cfg->lane_count++;
            }
            cur = end + 1;
        }
    }

    free(buf);
    return true;
}

bool save_config_file(const AppConfig* cfg, const char* filename) {
    FILE* f = fopen(filename, "w");
    if (!f) return false;

    fprintf(f, "{\n");
    fprintf(f, "  \"bbox\": [%d, %d, %d, %d],\n", cfg->bbox_left, cfg->bbox_top, cfg->bbox_right, cfg->bbox_bottom);
    fprintf(f, "  \"judgement_line\": %d,\n", cfg->judgement_line);
    fprintf(f, "  \"input_delay_ms\": %d,\n", cfg->input_delay_ms);
    fprintf(f, "  \"delay_ms\": %d,\n", cfg->input_delay_ms);
    fprintf(f, "  \"skill_level\": %d,\n", cfg->skill_level);
    fprintf(f, "  \"misread_chance\": %.4g,\n", cfg->misread_chance);
    fprintf(f, "  \"misread_ms\": %.4g,\n", cfg->misread_ms);
    fprintf(f, "  \"stamina_max\": %.4g,\n", cfg->stamina_max);
    fprintf(f, "  \"stamina_regen\": %.4g,\n", cfg->stamina_regen);
    fprintf(f, "  \"strain_step_pct\": %.4g,\n", cfg->strain_step_pct);
    fprintf(f, "  \"strain_misread_pct\": %.4g,\n", cfg->strain_misread_pct);
    fprintf(f, "  \"strain_skill_ms\": %.4g,\n", cfg->strain_skill_ms);
    fprintf(f, "  \"strain_regen_pct\": %.4g,\n", cfg->strain_regen_pct);
    fprintf(f, "  \"global_threshold\": %d,\n", cfg->global_threshold);
    fprintf(f, "  \"input_mode\": \"%s\",\n", cfg->input_mode);
    fprintf(f, "  \"lanes\": [\n");
    for (int i = 0; i < cfg->lane_count; i++) {
        fprintf(f, "    {\"name\": \"%s\", \"x\": %d, \"key\": \"%s\", \"threshold\": %d}%s\n",
            cfg->lanes[i].name,
            cfg->lanes[i].x,
            cfg->lanes[i].key_str,
            cfg->lanes[i].threshold,
            (i == cfg->lane_count - 1) ? "" : ",");
    }
    fprintf(f, "  ]\n");
    fprintf(f, "}\n");
    fclose(f);
    return true;
}

// Low-level fast keyboard input via SendInput
static inline void send_key_event(WORD vk, bool down) {
    INPUT input;
    ZeroMemory(&input, sizeof(INPUT));
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = vk;
    input.ki.wScan = (WORD)MapVirtualKeyA(vk, MAPVK_VK_TO_VSC);
    input.ki.dwFlags = down ? 0 : KEYEVENTF_KEYUP;
    SendInput(1, &input, sizeof(INPUT));
}

typedef struct {
    LONGLONG due_tick;
    WORD vk;
    bool down;
} DelayedKeyEvent;

#define MAX_DELAYED_EVENTS 1024
static DelayedKeyEvent g_delayed_queue[MAX_DELAYED_EVENTS];
static int g_delayed_count = 0;

static inline void queue_delayed_event(LONGLONG due_tick, WORD vk, bool down) {
    if (g_delayed_count >= MAX_DELAYED_EVENTS) return;
    int i = g_delayed_count++;
    while (i > 0) {
        int parent = (i - 1) / 2;
        if (g_delayed_queue[parent].due_tick <= due_tick) break;
        g_delayed_queue[i] = g_delayed_queue[parent];
        i = parent;
    }
    g_delayed_queue[i].due_tick = due_tick;
    g_delayed_queue[i].vk = vk;
    g_delayed_queue[i].down = down;
}

static inline void process_delayed_events(LONGLONG current_tick) {
    INPUT batch_inputs[64];
    int batch_count = 0;
    while (g_delayed_count > 0 && current_tick >= g_delayed_queue[0].due_tick) {
        WORD vk = g_delayed_queue[0].vk;
        bool down = g_delayed_queue[0].down;

        // Pop min element from heap
        DelayedKeyEvent last = g_delayed_queue[--g_delayed_count];
        if (g_delayed_count > 0) {
            int i = 0;
            while (i * 2 + 1 < g_delayed_count) {
                int left = i * 2 + 1;
                int right = left + 1;
                int best = left;
                if (right < g_delayed_count && g_delayed_queue[right].due_tick < g_delayed_queue[left].due_tick) {
                    best = right;
                }
                if (last.due_tick <= g_delayed_queue[best].due_tick) break;
                g_delayed_queue[i] = g_delayed_queue[best];
                i = best;
            }
            g_delayed_queue[i] = last;
        }

        if (batch_count < 64) {
            batch_inputs[batch_count].type = INPUT_KEYBOARD;
            batch_inputs[batch_count].ki.wVk = vk;
            batch_inputs[batch_count].ki.wScan = (WORD)MapVirtualKeyA(vk, MAPVK_VK_TO_VSC);
            batch_inputs[batch_count].ki.dwFlags = (down ? 0 : KEYEVENTF_KEYUP);
            batch_inputs[batch_count].ki.time = 0;
            batch_inputs[batch_count].ki.dwExtraInfo = 0;
            batch_count++;
        }
    }
    if (batch_count > 0) {
        SendInput((UINT)batch_count, batch_inputs, sizeof(INPUT));
    }
}

void release_all_keys(AppConfig* cfg) {
    for (int i = 0; i < cfg->lane_count; i++) {
        if (cfg->lanes[i].is_pressed) {
            send_key_event(cfg->lanes[i].vk, false);
            cfg->lanes[i].is_pressed = false;
        }
    }
}

// Ultra-fast GDI Capture with 32-bit DIBSection
bool init_capture(CaptureContext* ctx, int left, int top, int right, int bottom) {
    ctx->width = right - left;
    ctx->height = bottom - top;
    if (ctx->width <= 0) ctx->width = 1;
    if (ctx->height <= 0) ctx->height = 1;

    ctx->hScreenDC = GetDC(NULL);
    if (!ctx->hScreenDC) return false;

    ctx->hMemDC = CreateCompatibleDC(ctx->hScreenDC);
    if (!ctx->hMemDC) {
        ReleaseDC(NULL, ctx->hScreenDC);
        return false;
    }

    BITMAPINFO bmi;
    ZeroMemory(&bmi, sizeof(BITMAPINFO));
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bmi.bmiHeader.biWidth = ctx->width;
    bmi.bmiHeader.biHeight = -ctx->height; // Negative for top-down DIB layout
    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 32;
    bmi.bmiHeader.biCompression = BI_RGB;

    ctx->hBitmap = CreateDIBSection(ctx->hMemDC, &bmi, DIB_RGB_COLORS, &ctx->pBits, NULL, 0);
    if (!ctx->hBitmap || !ctx->pBits) {
        DeleteDC(ctx->hMemDC);
        ReleaseDC(NULL, ctx->hScreenDC);
        return false;
    }

    ctx->hOldBitmap = (HBITMAP)SelectObject(ctx->hMemDC, ctx->hBitmap);
    return true;
}

void cleanup_capture(CaptureContext* ctx) {
    if (ctx->hMemDC && ctx->hOldBitmap) {
        SelectObject(ctx->hMemDC, ctx->hOldBitmap);
    }
    if (ctx->hBitmap) DeleteObject(ctx->hBitmap);
    if (ctx->hMemDC) DeleteDC(ctx->hMemDC);
    if (ctx->hScreenDC) ReleaseDC(NULL, ctx->hScreenDC);
}

// Save captured buffer to BMP image
void save_screenshot_bmp(const CaptureContext* ctx, const char* filename) {
    FILE* f = fopen(filename, "wb");
    if (!f) {
        printf("[Screenshot Error] Could not write to %s\n", filename);
        return;
    }

    int row_bytes = ctx->width * 4;
    int image_size = row_bytes * ctx->height;

    BITMAPFILEHEADER bfh;
    ZeroMemory(&bfh, sizeof(BITMAPFILEHEADER));
    bfh.bfType = 0x4D42; // "BM"
    bfh.bfOffBits = sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER);
    bfh.bfSize = bfh.bfOffBits + image_size;

    BITMAPINFOHEADER bih;
    ZeroMemory(&bih, sizeof(BITMAPINFOHEADER));
    bih.biSize = sizeof(BITMAPINFOHEADER);
    bih.biWidth = ctx->width;
    bih.biHeight = -ctx->height; // top-down
    bih.biPlanes = 1;
    bih.biBitCount = 32;
    bih.biCompression = BI_RGB;
    bih.biSizeImage = image_size;

    fwrite(&bfh, sizeof(BITMAPFILEHEADER), 1, f);
    fwrite(&bih, sizeof(BITMAPINFOHEADER), 1, f);
    fwrite(ctx->pBits, 1, image_size, f);
    fclose(f);
    printf("[Screenshot] Saved detection strip to %s (%dx%d px)\n", filename, ctx->width, ctx->height);
}

// Interactive Console Menu
void print_menu(const AppConfig* cfg) {
    printf("\n=================================================================\n");
    printf("         OSU!MANIA PLAYER V1.3.0 - NATIVE C ENGINE\n");
    printf("=================================================================\n");
    printf("  BBox Detection:   (%d, %d, %d, %d) [Width: %d, Height: %d]\n",
        cfg->bbox_left, cfg->bbox_top, cfg->bbox_right, cfg->bbox_bottom,
        cfg->bbox_right - cfg->bbox_left, cfg->bbox_bottom - cfg->bbox_top);
    printf("  Judgement Line:   Y = %d\n", cfg->judgement_line);
    printf("  Input Delay:      %d ms\n", cfg->input_delay_ms);
    printf("  Skill Level:      %d ms (Variance: ±%d ms)\n", cfg->skill_level, cfg->skill_level);
    if (cfg->misread_chance > 0) {
        printf("  Misread:          %.4g%% chance, ignores lane for %.4g ms\n", cfg->misread_chance, cfg->misread_ms);
    } else {
        printf("  Misread:          Off\n");
    }
    if (cfg->stamina_max > 0) {
        printf("  Stamina:          %.4g max clicks, +%.4g per 20 ms\n", cfg->stamina_max, cfg->stamina_regen);
    } else {
        printf("  Stamina:          Off\n");
    }
    if (cfg->strain_step_pct > 0) {
        printf("  Strain:           Every %.4g%% stam lost: +%.4g%% misread, +%.4g ms jitter, -%.4g%% regen\n",
            cfg->strain_step_pct, cfg->strain_misread_pct, cfg->strain_skill_ms, cfg->strain_regen_pct);
    } else {
        printf("  Strain:           Off\n");
    }
    printf("  Input Mode:       %s\n", _stricmp(cfg->input_mode, "hold") == 0 ? "HOLD (Default)" : "TAP");
    printf("  Lanes (%d):\n", cfg->lane_count);
    for (int i = 0; i < cfg->lane_count; i++) {
        printf("    [%d] %-8s -> X: %-4d | Key: '%-5s' | Thresh: %d\n",
            i + 1, cfg->lanes[i].name, cfg->lanes[i].x, cfg->lanes[i].key_str, cfg->lanes[i].threshold);
    }
    printf("=================================================================\n");
    printf("  [Enter] / [1] Start Mania Player\n");
    printf("  [2] Configure Lanes (Add, Edit, Remove)\n");
    printf("  [3] Edit Detection BBox\n");
    printf("  [4] Change Global Threshold\n");
    printf("  [5] Change Input Delay (ms)\n");
    printf("  [6] Change Skill Level Variance (±ms)\n");
    printf("  [M] Configure Misread (chance %% + ignore ms)\n");
    printf("  [T] Configure Stamina (max clicks + regen per 20ms)\n");
    printf("  [R] Configure Strain (stamina depletion debuffs)\n");
    printf("  [7] Toggle Input Mode (Hold vs Tap)\n");
    printf("  [8] Reset to Default WhiteCat 23-Speed Preset\n");
    printf("  [9] Save Configuration to %s\n", CONFIG_FILE);
    printf("  [0] / [Q] Exit\n");
    printf("=================================================================\n");
    printf("Select option (or press Enter to start): ");
}

void configure_lanes_menu(AppConfig* cfg) {
    char line[128];
    while (true) {
        printf("\n--- LANE CONFIGURATION ---\n");
        for (int i = 0; i < cfg->lane_count; i++) {
            printf("  [%d] %-8s: X=%-4d Key='%s' Thresh=%d\n",
                i + 1, cfg->lanes[i].name, cfg->lanes[i].x, cfg->lanes[i].key_str, cfg->lanes[i].threshold);
        }
        printf("  [A] Add new lane\n");
        printf("  [D] Delete a lane\n");
        printf("  [B] Back to main menu\n");
        printf("Choice: ");

        if (!fgets(line, sizeof(line), stdin)) break;
        if (line[0] == 'b' || line[0] == 'B' || line[0] == '\n') break;

        if (line[0] == 'a' || line[0] == 'A') {
            if (cfg->lane_count >= MAX_LANES) {
                printf("[Error] Max lane limit reached (%d).\n", MAX_LANES);
                continue;
            }
            int idx = cfg->lane_count;
            printf("Lane name: ");
            if (fgets(cfg->lanes[idx].name, sizeof(cfg->lanes[idx].name), stdin)) {
                cfg->lanes[idx].name[strcspn(cfg->lanes[idx].name, "\r\n")] = 0;
            }
            if (strlen(cfg->lanes[idx].name) == 0) sprintf(cfg->lanes[idx].name, "Lane %d", idx + 1);

            printf("X offset in judgement box: ");
            int x = 0;
            if (scanf("%d", &x) == 1) cfg->lanes[idx].x = x;
            while (getchar() != '\n'); // flush

            printf("Key (e.g. q, w, space, left, up): ");
            if (fgets(cfg->lanes[idx].key_str, sizeof(cfg->lanes[idx].key_str), stdin)) {
                cfg->lanes[idx].key_str[strcspn(cfg->lanes[idx].key_str, "\r\n")] = 0;
            }
            cfg->lanes[idx].vk = resolve_vk(cfg->lanes[idx].key_str);
            cfg->lanes[idx].threshold = cfg->global_threshold;
            cfg->lanes[idx].is_pressed = false;
            cfg->lane_count++;
            printf("[Added] %s (X=%d, Key='%s')\n", cfg->lanes[idx].name, cfg->lanes[idx].x, cfg->lanes[idx].key_str);
        } else if (line[0] == 'd' || line[0] == 'D') {
            printf("Enter lane number to delete (1-%d): ", cfg->lane_count);
            int del_idx = 0;
            if (scanf("%d", &del_idx) == 1 && del_idx >= 1 && del_idx <= cfg->lane_count) {
                del_idx--;
                for (int i = del_idx; i < cfg->lane_count - 1; i++) {
                    cfg->lanes[i] = cfg->lanes[i + 1];
                }
                cfg->lane_count--;
                printf("[Deleted] Lane successfully removed.\n");
            }
            while (getchar() != '\n');
        } else if (atoi(line) >= 1 && atoi(line) <= cfg->lane_count) {
            int idx = atoi(line) - 1;
            printf("Editing %s:\n", cfg->lanes[idx].name);
            printf("New X offset [%d]: ", cfg->lanes[idx].x);
            char temp[64];
            if (fgets(temp, sizeof(temp), stdin) && temp[0] != '\n') {
                cfg->lanes[idx].x = atoi(temp);
            }
            printf("New Key [%s]: ", cfg->lanes[idx].key_str);
            if (fgets(temp, sizeof(temp), stdin) && temp[0] != '\n') {
                temp[strcspn(temp, "\r\n")] = 0;
                strcpy(cfg->lanes[idx].key_str, temp);
                cfg->lanes[idx].vk = resolve_vk(temp);
            }
            printf("Custom Threshold [%d]: ", cfg->lanes[idx].threshold);
            if (fgets(temp, sizeof(temp), stdin) && temp[0] != '\n') {
                cfg->lanes[idx].threshold = atoi(temp);
            }
            printf("[Updated] %s: X=%d Key='%s' Thresh=%d\n",
                cfg->lanes[idx].name, cfg->lanes[idx].x, cfg->lanes[idx].key_str, cfg->lanes[idx].threshold);
        }
    }
}

void edit_bbox_menu(AppConfig* cfg) {
    printf("\nCurrent BBox: (%d, %d, %d, %d)\n",
        cfg->bbox_left, cfg->bbox_top, cfg->bbox_right, cfg->bbox_bottom);
    printf("Enter 4 integers: left top right bottom (or press Enter to keep): ");
    char line[128];
    if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
        int l, t, r, b;
        if (sscanf(line, "%d %d %d %d", &l, &t, &r, &b) == 4 ||
            sscanf(line, "%d, %d, %d, %d", &l, &t, &r, &b) == 4) {
            cfg->bbox_left = l;
            cfg->bbox_top = t;
            cfg->bbox_right = r;
            cfg->bbox_bottom = b;
            printf("[Updated] BBox set to (%d, %d, %d, %d)\n", l, t, r, b);
        } else {
            printf("[Error] Invalid input. Must be 4 integers.\n");
        }
    }
}

// ---- Skill simulation: Misread, Stamina & Strain ----
static LONGLONG g_misread_until[MAX_LANES];
static double g_stamina = 0.0;
static LONGLONG g_stamina_last = 0;
static int g_eff_skill_level = 0;

static void skill_gate_init(const AppConfig* cfg, LONGLONG now) {
    for (int i = 0; i < MAX_LANES; i++) g_misread_until[i] = 0;
    g_stamina = (double)cfg->stamina_max;
    g_stamina_last = now;
    g_eff_skill_level = cfg->skill_level;
}

// Returns false when the note press on this lane should be ignored.
static bool skill_allow_press(const AppConfig* cfg, int lane, LONGLONG now, LONGLONG freq) {
    double eff_misread_chance = cfg->misread_chance;
    g_eff_skill_level = cfg->skill_level;

    if (cfg->stamina_max > 0) {
        double dt_sec = (double)(now - g_stamina_last) / (double)freq;
        g_stamina_last = now;

        double lost_pct = (1.0 - (g_stamina / (double)cfg->stamina_max)) * 100.0;
        if (lost_pct < 0.0) lost_pct = 0.0;
        int steps = (cfg->strain_step_pct > 0) ? (int)(lost_pct / cfg->strain_step_pct) : 0;

        double regen_factor = 1.0 - ((double)steps * (cfg->strain_regen_pct / 100.0));
        if (regen_factor < 0.0) regen_factor = 0.0;
        double eff_regen_per_sec = cfg->stamina_regen * 50.0 * regen_factor;

        g_stamina += dt_sec * eff_regen_per_sec;
        if (g_stamina > cfg->stamina_max) g_stamina = cfg->stamina_max;

        lost_pct = (1.0 - (g_stamina / cfg->stamina_max)) * 100.0;
        if (lost_pct < 0.0) lost_pct = 0.0;
        steps = (cfg->strain_step_pct > 0) ? (int)(lost_pct / cfg->strain_step_pct) : 0;

        eff_misread_chance = cfg->misread_chance + (steps * cfg->strain_misread_pct);
        if (eff_misread_chance < 0.0) eff_misread_chance = 0.0;
        if (eff_misread_chance > 100.0) eff_misread_chance = 100.0;

        g_eff_skill_level = cfg->skill_level + (int)(steps * cfg->strain_skill_ms);
        if (g_eff_skill_level < 0) g_eff_skill_level = 0;
    }

    if (eff_misread_chance > 0.0) {
        if (now < g_misread_until[lane]) return false;
        if (((double)rand() / (double)RAND_MAX * 100.0) < eff_misread_chance) {
            g_misread_until[lane] = now + ((LONGLONG)(cfg->misread_ms * (double)freq)) / 1000;
            return false;
        }
    }

    if (cfg->stamina_max > 0) {
        if (g_stamina < 1.0) return false;
        g_stamina -= 1.0;
        double lost_pct = (1.0 - (g_stamina / cfg->stamina_max)) * 100.0;
        if (lost_pct < 0.0) lost_pct = 0.0;
        int steps = (cfg->strain_step_pct > 0) ? (int)(lost_pct / cfg->strain_step_pct) : 0;
        g_eff_skill_level = cfg->skill_level + (int)(steps * cfg->strain_skill_ms);
        if (g_eff_skill_level < 0) g_eff_skill_level = 0;
    }
    return true;
}

// Main high-performance gameplay loop in C
void run_player(AppConfig* cfg) {
    CaptureContext ctx;
    if (!init_capture(&ctx, cfg->bbox_left, cfg->bbox_top, cfg->bbox_right, cfg->bbox_bottom)) {
        printf("[Fatal Error] Failed to initialize Windows GDI Capture context.\n");
        return;
    }

    // Refresh lane virtual keys
    for (int i = 0; i < cfg->lane_count; i++) {
        cfg->lanes[i].vk = resolve_vk(cfg->lanes[i].key_str);
        cfg->lanes[i].is_pressed = false;
    }

    printf("\n=================================================================\n");
    printf("         OSU!MANIA PLAYER V1.3.0 (NATIVE C) - RUNNING\n");
    printf("  Controls:\n");
    printf("    [F] Start / Play\n");
    printf("    [S] Stop / Pause\n");
    printf("    [D] Save Screenshot (Screenshot.bmp)\n");
    printf("    [M] Pause & Return to Configuration Menu\n");
    printf("    [/] Clean Exit\n");
    printf("=================================================================\n\n");

    LARGE_INTEGER freq, t_start, t_now;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t_start);

    long long frame_count = 0;
    bool hold_mode = (_stricmp(cfg->input_mode, "hold") == 0);
    int line_y = cfg->judgement_line;
    if (line_y >= ctx.height) line_y = ctx.height - 1;
    if (line_y < 0) line_y = 0;

    int width = ctx.width;
    const uint32_t* pPixels = (const uint32_t*)ctx.pBits;

    int lane_pixel_idx[MAX_LANES];
    int thresh_sums[MAX_LANES];
    WORD lane_vks[MAX_LANES];
    LONGLONG lane_hold_ticks[MAX_LANES];
    bool lane_valid[MAX_LANES];
    bool lane_skipped[MAX_LANES];

    for (int i = 0; i < cfg->lane_count; i++) {
        int lx = cfg->lanes[i].x;
        if (lx >= 0 && lx < width && line_y >= 0 && line_y < ctx.height) {
            lane_pixel_idx[i] = line_y * width + lx;
            thresh_sums[i] = cfg->lanes[i].threshold * 3;
            lane_vks[i] = cfg->lanes[i].vk;
            lane_valid[i] = true;
        } else {
            lane_pixel_idx[i] = -1;
            lane_valid[i] = false;
        }
        lane_hold_ticks[i] = 0;
        lane_skipped[i] = false;
    }

    g_delayed_count = 0;
    bool has_delay_or_skill = (cfg->input_delay_ms > 0 || cfg->skill_level > 0 || cfg->strain_skill_ms > 0);
    bool skill_gate = (cfg->misread_chance > 0 || cfg->stamina_max > 0 || cfg->strain_step_pct > 0);
    {
        LARGE_INTEGER t_init;
        QueryPerformanceCounter(&t_init);
        skill_gate_init(cfg, t_init.QuadPart);
    }

    while (g_program_active) {
        // Hotkey polling via GetAsyncKeyState
        if (GetAsyncKeyState('F') & 0x8000) {
            if (!g_is_running) {
                printf("\n[>> START] Mania Player active! Monitoring %d lanes...\n", cfg->lane_count);
                g_is_running = true;
            }
            Sleep(150); // Debounce hotkey
        }
        if (GetAsyncKeyState('S') & 0x8000) {
            if (g_is_running) {
                printf("\n[|| STOP] Mania Player paused.\n");
                g_is_running = false;
                g_delayed_count = 0;
                release_all_keys(cfg);
            }
            Sleep(150);
        }
        if (GetAsyncKeyState('D') & 0x8000) {
            BitBlt(ctx.hMemDC, 0, 0, ctx.width, ctx.height, ctx.hScreenDC, cfg->bbox_left, cfg->bbox_top, SRCCOPY);
            save_screenshot_bmp(&ctx, SCREENSHOT_FILE);
            Sleep(250);
        }
        if (GetAsyncKeyState('M') & 0x8000) {
            printf("\n[Menu] Returning to Configuration Menu...\n");
            g_is_running = false;
            g_delayed_count = 0;
            release_all_keys(cfg);
            Sleep(250);
            break;
        }
        if (GetAsyncKeyState(VK_OEM_2) & 0x8000) { // '/' key
            printf("\n[XX EXIT] Exiting Mania Player...\n");
            g_is_running = false;
            g_program_active = false;
            g_delayed_count = 0;
            release_all_keys(cfg);
            break;
        }

        if (!g_is_running) {
            Sleep(10);
            continue;
        }

        // Process due delayed events before screen capture
        QueryPerformanceCounter(&t_now);
        if (has_delay_or_skill) {
            process_delayed_events(t_now.QuadPart);
        }

        // 1. Ultra-fast direct memory screen capture
        BitBlt(ctx.hMemDC, 0, 0, width, ctx.height, ctx.hScreenDC, cfg->bbox_left, cfg->bbox_top, SRCCOPY);

        QueryPerformanceCounter(&t_now);
        if (has_delay_or_skill) {
            process_delayed_events(t_now.QuadPart);
        }

        // 2. Direct 32-bit aligned memory pixel inspection with batch SendInput
        INPUT frame_inputs[MAX_LANES * 2];
        int frame_batch_count = 0;

        for (int i = 0; i < cfg->lane_count; i++) {
            if (!lane_valid[i]) continue;

            uint32_t px = pPixels[lane_pixel_idx[i]];
            int sum_bgr = (px & 0xFF) + ((px >> 8) & 0xFF) + ((px >> 16) & 0xFF);
            bool is_active = (sum_bgr > thresh_sums[i]);
            bool was_active = cfg->lanes[i].is_pressed;

            if (hold_mode) {
                if (is_active && !was_active) {
                    if (skill_gate && !skill_allow_press(cfg, i, t_now.QuadPart, freq.QuadPart)) {
                        lane_skipped[i] = true;
                        cfg->lanes[i].is_pressed = true;
                        continue;
                    }
                    lane_skipped[i] = false;
                    if (has_delay_or_skill) {
                        int var_ms = 0;
                        int eff_sk = (g_eff_skill_level >= 0) ? g_eff_skill_level : cfg->skill_level;
                        if (eff_sk > 0) {
                            int range = (eff_sk * 2) + 1;
                            var_ms = (rand() % range) - eff_sk;
                        }
                        int eff_delay_ms = cfg->input_delay_ms + var_ms;
                        if (eff_delay_ms < 0) eff_delay_ms = 0;
                        LONGLONG eff_ticks = ((LONGLONG)eff_delay_ms * freq.QuadPart) / 1000;
                        lane_hold_ticks[i] = eff_ticks;

                        if (eff_ticks > 0) {
                            queue_delayed_event(t_now.QuadPart + eff_ticks, lane_vks[i], true);
                        } else {
                            frame_inputs[frame_batch_count].type = INPUT_KEYBOARD;
                            frame_inputs[frame_batch_count].ki.wVk = lane_vks[i];
                            frame_inputs[frame_batch_count].ki.wScan = (WORD)MapVirtualKeyA(lane_vks[i], MAPVK_VK_TO_VSC);
                            frame_inputs[frame_batch_count].ki.dwFlags = 0;
                            frame_inputs[frame_batch_count].ki.time = 0;
                            frame_inputs[frame_batch_count].ki.dwExtraInfo = 0;
                            frame_batch_count++;
                        }
                    } else {
                        frame_inputs[frame_batch_count].type = INPUT_KEYBOARD;
                        frame_inputs[frame_batch_count].ki.wVk = lane_vks[i];
                        frame_inputs[frame_batch_count].ki.wScan = (WORD)MapVirtualKeyA(lane_vks[i], MAPVK_VK_TO_VSC);
                        frame_inputs[frame_batch_count].ki.dwFlags = 0;
                        frame_inputs[frame_batch_count].ki.time = 0;
                        frame_inputs[frame_batch_count].ki.dwExtraInfo = 0;
                        frame_batch_count++;
                    }
                    cfg->lanes[i].is_pressed = true;
                } else if (!is_active && was_active) {
                    if (lane_skipped[i]) {
                        lane_skipped[i] = false;
                        cfg->lanes[i].is_pressed = false;
                        continue;
                    }
                    if (has_delay_or_skill) {
                        LONGLONG eff_ticks = lane_hold_ticks[i];
                        if (eff_ticks > 0) {
                            queue_delayed_event(t_now.QuadPart + eff_ticks, lane_vks[i], false);
                        } else {
                            frame_inputs[frame_batch_count].type = INPUT_KEYBOARD;
                            frame_inputs[frame_batch_count].ki.wVk = lane_vks[i];
                            frame_inputs[frame_batch_count].ki.wScan = (WORD)MapVirtualKeyA(lane_vks[i], MAPVK_VK_TO_VSC);
                            frame_inputs[frame_batch_count].ki.dwFlags = KEYEVENTF_KEYUP;
                            frame_inputs[frame_batch_count].ki.time = 0;
                            frame_inputs[frame_batch_count].ki.dwExtraInfo = 0;
                            frame_batch_count++;
                        }
                    } else {
                        frame_inputs[frame_batch_count].type = INPUT_KEYBOARD;
                        frame_inputs[frame_batch_count].ki.wVk = lane_vks[i];
                        frame_inputs[frame_batch_count].ki.wScan = (WORD)MapVirtualKeyA(lane_vks[i], MAPVK_VK_TO_VSC);
                        frame_inputs[frame_batch_count].ki.dwFlags = KEYEVENTF_KEYUP;
                        frame_inputs[frame_batch_count].ki.time = 0;
                        frame_inputs[frame_batch_count].ki.dwExtraInfo = 0;
                        frame_batch_count++;
                    }
                    cfg->lanes[i].is_pressed = false;
                }
            } else { // Tap mode
                if (is_active && !was_active) {
                    if (skill_gate && !skill_allow_press(cfg, i, t_now.QuadPart, freq.QuadPart)) {
                        cfg->lanes[i].is_pressed = true;
                        continue;
                    }
                    if (has_delay_or_skill) {
                        int var_ms = 0;
                        int eff_sk = (g_eff_skill_level >= 0) ? g_eff_skill_level : cfg->skill_level;
                        if (eff_sk > 0) {
                            int range = (eff_sk * 2) + 1;
                            var_ms = (rand() % range) - eff_sk;
                        }
                        int eff_delay_ms = cfg->input_delay_ms + var_ms;
                        if (eff_delay_ms < 0) eff_delay_ms = 0;
                        LONGLONG eff_ticks = ((LONGLONG)eff_delay_ms * freq.QuadPart) / 1000;
                        LONGLONG tap_up_ticks = eff_ticks + ((LONGLONG)20 * freq.QuadPart / 1000);

                        if (eff_ticks > 0) {
                            queue_delayed_event(t_now.QuadPart + eff_ticks, lane_vks[i], true);
                            queue_delayed_event(t_now.QuadPart + tap_up_ticks, lane_vks[i], false);
                        } else {
                            frame_inputs[frame_batch_count].type = INPUT_KEYBOARD;
                            frame_inputs[frame_batch_count].ki.wVk = lane_vks[i];
                            frame_inputs[frame_batch_count].ki.wScan = (WORD)MapVirtualKeyA(lane_vks[i], MAPVK_VK_TO_VSC);
                            frame_inputs[frame_batch_count].ki.dwFlags = 0;
                            frame_inputs[frame_batch_count].ki.time = 0;
                            frame_inputs[frame_batch_count].ki.dwExtraInfo = 0;
                            frame_batch_count++;

                            queue_delayed_event(t_now.QuadPart + ((LONGLONG)20 * freq.QuadPart / 1000), lane_vks[i], false);
                        }
                    } else {
                        frame_inputs[frame_batch_count].type = INPUT_KEYBOARD;
                        frame_inputs[frame_batch_count].ki.wVk = lane_vks[i];
                        frame_inputs[frame_batch_count].ki.wScan = (WORD)MapVirtualKeyA(lane_vks[i], MAPVK_VK_TO_VSC);
                        frame_inputs[frame_batch_count].ki.dwFlags = 0;
                        frame_inputs[frame_batch_count].ki.time = 0;
                        frame_inputs[frame_batch_count].ki.dwExtraInfo = 0;
                        frame_batch_count++;

                        queue_delayed_event(t_now.QuadPart + ((LONGLONG)20 * freq.QuadPart / 1000), lane_vks[i], false);
                    }
                    cfg->lanes[i].is_pressed = true;
                } else if (!is_active && was_active) {
                    cfg->lanes[i].is_pressed = false;
                }
            }
        }

        if (frame_batch_count > 0) {
            SendInput((UINT)frame_batch_count, frame_inputs, sizeof(INPUT));
        }

        frame_count++;

        // Periodic FPS display
        QueryPerformanceCounter(&t_now);
        double elapsed_sec = (double)(t_now.QuadPart - t_start.QuadPart) / (double)freq.QuadPart;
        if (elapsed_sec >= 2.0) {
            double fps = (double)frame_count / elapsed_sec;
            double latency_ms = (elapsed_sec / (double)frame_count) * 1000.0;
            printf("\r[Native C Active] FPS: %6.1f | Latency: %5.2f ms | Delay: %d ms | Skill: ±%d ms | Lanes: %d   ",
                fps, latency_ms, cfg->input_delay_ms, cfg->skill_level, cfg->lane_count);
            fflush(stdout);
            frame_count = 0;
            t_start = t_now;
        }
    }

    g_delayed_count = 0;

    release_all_keys(cfg);
    cleanup_capture(&ctx);
}

int main() {
    SetConsoleTitleA("Osu!Mania Player v1.3.0");
    srand((unsigned)GetTickCount() ^ ((unsigned)GetCurrentProcessId() << 16));
    CreateDirectoryA("presets", NULL);
    CreateDirectoryA("backups", NULL);
    timeBeginPeriod(1);

    set_default_config(&g_config);
    if (!load_config_file(&g_config, CONFIG_FILE)) {
        save_config_file(&g_config, CONFIG_FILE);
    }

    char line[64];
    while (g_program_active) {
        print_menu(&g_config);
        if (!fgets(line, sizeof(line), stdin)) break;

        char choice = line[0];
        if (choice == '\n' || choice == '1') {
            save_config_file(&g_config, CONFIG_FILE);
            run_player(&g_config);
        } else if (choice == '2') {
            configure_lanes_menu(&g_config);
        } else if (choice == '3') {
            edit_bbox_menu(&g_config);
        } else if (choice == '4') {
            printf("Enter global threshold 0-255 [%d]: ", g_config.global_threshold);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                g_config.global_threshold = atoi(line);
                printf("[Updated] Global threshold set to %d\n", g_config.global_threshold);
            }
        } else if (choice == '5') {
            printf("Enter input delay in milliseconds (0-5000) [%d]: ", g_config.input_delay_ms);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                int d = atoi(line);
                if (d < 0) d = 0;
                g_config.input_delay_ms = d;
                printf("[Updated] Input delay set to %d ms\n", g_config.input_delay_ms);
            }
        } else if (choice == '6' || choice == 'k' || choice == 'K' || choice == 's' || choice == 'S') {
            printf("Enter skill level variance in milliseconds (0-500) [±%d ms]: ", g_config.skill_level);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                int sk = atoi(line);
                if (sk < 0) sk = 0;
                if (sk > 500) sk = 500;
                g_config.skill_level = sk;
                printf("[Updated] Skill level set to ±%d ms variance\n", g_config.skill_level);
            }
        } else if (choice == 'm' || choice == 'M') {
            printf("Enter misread chance %% (0-100, 0 = off) [%.4g]: ", g_config.misread_chance);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                double c = atof(line);
                if (c < 0.0) c = 0.0;
                if (c > 100.0) c = 100.0;
                g_config.misread_chance = c;
            }
            printf("Enter ignore duration in ms (0-5000) [%.4g]: ", g_config.misread_ms);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                double d = atof(line);
                if (d < 0.0) d = 0.0;
                if (d > 5000.0) d = 5000.0;
                g_config.misread_ms = d;
            }
            printf("[Updated] Misread: %.4g%% chance, ignores lane for %.4g ms\n", g_config.misread_chance, g_config.misread_ms);
        } else if (choice == 't' || choice == 'T') {
            printf("Enter stamina max clicks (0 = off) [%.4g]: ", g_config.stamina_max);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                double m = atof(line);
                if (m < 0.0) m = 0.0;
                g_config.stamina_max = m;
            }
            printf("Enter stamina regeneration per 20 ms [%.4g]: ", g_config.stamina_regen);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                double r = atof(line);
                if (r < 0.0) r = 0.0;
                g_config.stamina_regen = r;
            }
            printf("[Updated] Stamina: %.4g max clicks, +%.4g per 20 ms\n", g_config.stamina_max, g_config.stamina_regen);
        } else if (choice == 'r' || choice == 'R') {
            printf("Enter strain step %% lost stamina (0 = off) [%.4g]: ", g_config.strain_step_pct);
            if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                double p = atof(line);
                if (p < 0.0) p = 0.0;
                if (p > 100.0) p = 100.0;
                g_config.strain_step_pct = p;
            }
            if (g_config.strain_step_pct > 0.0) {
                printf("Enter misread chance increase %% per step [%.4g]: ", g_config.strain_misread_pct);
                if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                    double m = atof(line);
                    if (m < 0.0) m = 0.0;
                    if (m > 100.0) m = 100.0;
                    g_config.strain_misread_pct = m;
                }
                printf("Enter skill jitter delay increase in ms per step [%.4g]: ", g_config.strain_skill_ms);
                if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                    double s = atof(line);
                    if (s < 0.0) s = 0.0;
                    if (s > 500.0) s = 500.0;
                    g_config.strain_skill_ms = s;
                }
                printf("Enter stamina regen reduction %% per step [%.4g]: ", g_config.strain_regen_pct);
                if (fgets(line, sizeof(line), stdin) && line[0] != '\n') {
                    double r = atof(line);
                    if (r < 0.0) r = 0.0;
                    if (r > 100.0) r = 100.0;
                    g_config.strain_regen_pct = r;
                }
                printf("[Updated] Strain: Every %.4g%% lost -> +%.4g%% misread, +%.4g ms jitter, -%.4g%% regen\n",
                    g_config.strain_step_pct, g_config.strain_misread_pct, g_config.strain_skill_ms, g_config.strain_regen_pct);
            } else {
                printf("[Updated] Strain disabled.\n");
            }
        } else if (choice == '7') {
            if (_stricmp(g_config.input_mode, "hold") == 0) {
                strcpy(g_config.input_mode, "tap");
            } else {
                strcpy(g_config.input_mode, "hold");
            }
            printf("[Updated] Mode toggled to: %s\n", g_config.input_mode);
        } else if (choice == '8') {
            set_default_config(&g_config);
            save_config_file(&g_config, CONFIG_FILE);
            printf("[Reset] Restored default WhiteCat 23-speed preset.\n");
        } else if (choice == '9') {
            save_config_file(&g_config, CONFIG_FILE);
            printf("[Saved] Saved settings to %s\n", CONFIG_FILE);
        } else if (choice == '0' || choice == 'q' || choice == 'Q') {
            printf("\nExiting Mania Player. Goodbye!\n");
            break;
        } else {
            printf("[Invalid] Please choose a valid option.\n");
        }
    }

    timeEndPeriod(1);
    return 0;
}
