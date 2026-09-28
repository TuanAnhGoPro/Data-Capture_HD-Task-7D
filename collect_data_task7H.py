import csv, os, time
from datetime import datetime, timedelta
import serial

PORT, BAUD = "COM3", 9600
DURATION_HOURS = 1
OUT_FILE, ERR_FILE = "raw_data_v2.csv", "errors_v2.log"
RECONNECT_DELAY = 5
WATCHDOG_S = 400
FIELDS = ["timestamp", "seq", "temperature", "humidity", "motion", "motion_count", "dht_retries"]


def log_err(msg):
    line = f"{datetime.now().isoformat()} {msg}"
    print("[WARN]", line)
    with open(ERR_FILE, "a") as f:
        f.write(line + "\n")


def connect():
    while True:
        try:
            s = serial.Serial(PORT, BAUD, timeout=1)
            time.sleep(2)
            print(f"Connected to {PORT}")
            return s
        except serial.SerialException as e:
            log_err(f"cannot open {PORT}: {e}; retry in {RECONNECT_DELAY}s")
            time.sleep(RECONNECT_DELAY)


def parse(line):
    """'seq,t,h,motion,count,retries' -> dict, hoac None neu sai."""
    p = line.split(",")
    if p[0] == "ERR":
        log_err(f"arduino reported: {line}")
        return None
    if len(p) != 6:
        log_err(f"malformed line: {line!r}")
        return None
    try:
        r = dict(seq=int(p[0]), temperature=float(p[1]), humidity=float(p[2]),
                 motion=int(p[3]), motion_count=int(p[4]), dht_retries=int(p[5]))
    except ValueError:
        log_err(f"non-numeric: {line!r}")
        return None
    if not (-40 <= r["temperature"] <= 80 and 0 <= r["humidity"] <= 100):
        log_err(f"out of range: {line!r}")
        return None
    return r


def main():
    end = datetime.now() + timedelta(hours=DURATION_HOURS)
    new_file = not os.path.exists(OUT_FILE)
    f = open(OUT_FILE, "a", newline="")
    w = csv.DictWriter(f, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
    ser, last_seq, last_rx = connect(), None, time.time()
    stats = dict(rows=0, lost=0, errors=0, reconnects=0)
    try:
        while datetime.now() < end:
            try:
                line = ser.readline().decode(errors="ignore").strip()
            except (serial.SerialException, OSError):
                stats["reconnects"] += 1
                log_err("serial lost, reconnecting")
                try: ser.close()
                except Exception: pass
                ser = connect()
                continue
            if not line:
                if time.time() - last_rx > WATCHDOG_S:
                    log_err(f"watchdog: no data for {time.time() - last_rx:.0f}s")
                    last_rx = time.time()
                continue
            last_rx = time.time()
            if line.startswith("ERR,"):
                try:
                    last_seq = int(line.split(",")[1])   # an ERR sample still consumes a seq number
                except (IndexError, ValueError):
                    pass
            r = parse(line)
            if r is None:
                stats["errors"] += 1
                continue
            if last_seq is not None and r["seq"] > last_seq + 1:
                missing = r["seq"] - last_seq - 1
                stats["lost"] += missing
                log_err(f"gap: {missing} sample(s) missing between seq {last_seq} and {r['seq']}")
            if last_seq is not None and r["seq"] <= last_seq:
                log_err(f"seq reset {last_seq}->{r['seq']} (Arduino rebooted?)")
            last_seq = r["seq"]
            r["timestamp"] = datetime.now().isoformat()
            w.writerow(r)
            f.flush(); os.fsync(f.fileno())            # ghi xuong dia ngay
            stats["rows"] += 1
            print(r)
    except KeyboardInterrupt:
        print("Stopped by user")
    finally:
        f.close()
        try: ser.close()
        except Exception: pass
        total = stats["rows"] + stats["lost"]
        print("SUMMARY", stats, f"completeness={stats['rows']/total*100:.1f}%" if total else "")


if __name__ == "__main__":
    main()
