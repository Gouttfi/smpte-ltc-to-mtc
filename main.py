import pyaudio
import audioop
import time
import threading
import mido
import mido.backends.rtmidi
import tkinter as tk

# Initialisation of the LTC listener
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
CHUNK = 2048
SYNC_WORD = '0011111111111101'
jam = '00:00:00:00'
now_tc = '00:00:00:00'
last_cam = '-1'
jam_advice = False
jammed = False
codes = [49,50,51,52,53,54,55,56,57,48]
cams = {}

for i,j in enumerate(codes):
    cams[j] = str(i+1)
    
def bin_to_bytes(a,size=1):
    ret = int(a,2).to_bytes(size,byteorder='little')
    return ret

def bin_to_int(a):
    out = 0
    for i,j in enumerate(a):
        out += int(j)*2**i
    return out

def decode_frame(frame):
    o = {}
    o['frame_units'] = bin_to_int(frame[:4])
    o['user_bits_1'] = int.from_bytes(bin_to_bytes(frame[4:8]),byteorder='little')
    o['frame_tens'] = bin_to_int(frame[8:10])
    o['drop_frame'] = int.from_bytes(bin_to_bytes(frame[10]),byteorder='little')
    o['color_frame'] = int.from_bytes(bin_to_bytes(frame[11]),byteorder='little')
    o['user_bits_2'] = int.from_bytes(bin_to_bytes(frame[12:16]),byteorder='little')
    o['sec_units'] = bin_to_int(frame[16:20])
    o['user_bits_3'] = int.from_bytes(bin_to_bytes(frame[20:24]),byteorder='little')
    o['sec_tens'] = bin_to_int(frame[24:27])
    o['flag_1'] = int.from_bytes(bin_to_bytes(frame[27]),byteorder='little')
    o['user_bits_4'] = int.from_bytes(bin_to_bytes(frame[28:32]),byteorder='little')
    o['min_units'] = bin_to_int(frame[32:36])
    o['user_bits_5'] = int.from_bytes(bin_to_bytes(frame[36:40]),byteorder='little')
    o['min_tens'] = bin_to_int(frame[40:43])
    o['flag_2'] = int.from_bytes(bin_to_bytes(frame[43]),byteorder='little')
    o['user_bits_6'] = int.from_bytes(bin_to_bytes(frame[44:48]),byteorder='little')
    o['hour_units'] = bin_to_int(frame[48:52])
    o['user_bits_7'] = int.from_bytes(bin_to_bytes(frame[52:56]),byteorder='little')
    o['hour_tens'] = bin_to_int(frame[56:58])
    o['bgf'] = int.from_bytes(bin_to_bytes(frame[58]),byteorder='little')
    o['flag_3'] = int.from_bytes(bin_to_bytes(frame[59]),byteorder='little')
    o['user_bits_8'] = int.from_bytes(bin_to_bytes(frame[60:64]),byteorder='little')
    o['sync_word'] = int.from_bytes(bin_to_bytes(frame[64:],2),byteorder='little')
    o['formatted_tc'] = "{:02d}:{:02d}:{:02d}:{:02d}".format(
        o['hour_tens']*10+o['hour_units'],
        o['min_tens']*10+o['min_units'],
        o['sec_tens']*10+o['sec_units'],
        o['frame_tens']*10+o['frame_units'],
    )
    return o

def print_tc():
    global jam,now_tc

    freq = str_frequency_to_int(selected_frequency.get())
    inter = 1/freq
    last_jam = jam
    h,m,s,f = [int(x) for x in jam.split(':')]
    while enable_listening.get():
        if jam == None:
            break
        if jam != last_jam:
            h,m,s,f = [int(x) for x in jam.split(':')]
            last_jam = jam
        tcp = "{:02d}:{:02d}:{:02d}:{:02d}".format(h,m,s,f)

        if compare_timestamps(tcp,jam) < 1.5:
            send_mtc_signal(tcp)
            status_color.set("green")
        else:
            status_color.set("orange")
        status_square.configure(bg=status_color.get())
        now_tc = tcp
        time.sleep(inter)
        f += 1
        if f >= 24:
            f = 0
            s += 1
        if s >= 60:
            s = 0
            m += 1
        if m >= 60:
            m = 0
            h += 1

def decode_ltc(wave_frames):
    global jam
    frames = []
    output = ''
    last = None
    toggle = True
    sp = 1
    for i in range(0,len(wave_frames),2):
        data = wave_frames[i:i+2]
        pos = audioop.minmax(data,2)
        if pos[0] < 0:
            cyc = 'Neg'
        else:
            cyc = 'Pos'
        if cyc != last:
            if sp >= 7:
                if sp > 14:
                    bit = '0'
                    output += str(bit)
                else:
                    if toggle:
                        bit = '1'
                        output += str(bit)
                        toggle = False
                    else:
                        toggle = True
                if len(output) >= len(SYNC_WORD):
                    if output[-len(SYNC_WORD):] == SYNC_WORD:
                        if len(output) > 80:
                            frames.append(output[-80:])
                            output = ''
                            jam = decode_frame(frames[-1])['formatted_tc']
                            send_mtc_signal(jam)
            sp = 1
            last = cyc
        else:
            sp += 1

def loop_decode_ltc(stream,frames):
    data = stream.read(CHUNK)
    decode_ltc(data)
    frames.append(data)
    if enable_listening.get():
        frame.after(10,lambda:loop_decode_ltc(stream,frames))

def init_ltc_listener():

    micro_selectionne = selected_microphone_index.get()

    p = pyaudio.PyAudio()
    t = threading.Thread(target=print_tc)
    t.start()

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK,
                    input_device_index=micro_selectionne)

    frames = []
    loop_decode_ltc(stream,frames)

# Write in MIDI port the MTC values
def send_mtc_signal(timecode_str):
    midi_port = selected_midi.get()
    frequency = str_frequency_to_int(selected_frequency.get())

    # Verify timecode format (HH:MM:SS:FF)
    try:
        hours, minutes, seconds, frames = map(int, timecode_str.split(':'))
    except (ValueError, IndexError):
        raise ValueError("Invalid timecode format. Use HH:MM:SS:FF format (e.g., '01:23:45:15').")

    # Verify validity of numbers
    if not 0 <= hours < 24 or not 0 <= minutes < 60 or not 0 <= seconds < 60 or not 0 <= frames < 30:
        raise ValueError("Invalid timecode values. Hours should be in the range 0-23, minutes 0-59, seconds 0-59, and frames 0-29 (depending on frame rate).")

    # Calculating complete MTC message
    mtc_hours = decimal_to_hex_pair(hours)
    mtc_minutes = decimal_to_hex_pair(minutes)
    mtc_seconds = decimal_to_hex_pair(seconds)
    mtc_frames = decimal_to_hex_pair(frames)

    if frequency == 24:
        mtc_frequency = 0
    if frequency == 25:
        mtc_frequency = 1
    if frequency == 30:
        mtc_frequency = 2

    try:
        with mido.open_output(midi_port) as port:
            # Send MIDI messages
            message = mido.Message('quarter_frame', frame_type=0, frame_value=mtc_frames[1])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=1, frame_value=mtc_frames[0])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=2, frame_value=mtc_seconds[1])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=3, frame_value=mtc_seconds[0])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=4, frame_value=mtc_minutes[1])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=5, frame_value=mtc_minutes[0])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=6, frame_value=mtc_hours[1])
            port.send(message)
            message = mido.Message('quarter_frame', frame_type=7, frame_value=mtc_frequency)
            port.send(message)

    except (IOError, ValueError) as e:
        print(f"Error: {e}")

def decimal_to_hex_pair(decimal_value):
    binary_value = bin(decimal_value)[2:].zfill(8)

    first_4_bits = binary_value[:4]
    decimal_value_1 = int(first_4_bits, 2)

    last_4_bits = binary_value[4:]
    decimal_value_2 = int(last_4_bits, 2)

    return [decimal_value_1, decimal_value_2]

def time_to_seconds(time):
    hh, mm, ss, ff = map(int, time.split(':'))
    total_seconds = hh * 3600 + mm * 60 + ss + ff / 30
    return total_seconds

def compare_timestamps(timestamp1, timestamp2):
    return time_to_seconds(timestamp1) - time_to_seconds(timestamp2)

# Get available microphones list
def get_available_microphones():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    num_devices = info.get('deviceCount')

    microphones = []
    for i in range(num_devices):
        device_info = p.get_device_info_by_index(i)
        if device_info.get('maxInputChannels') > 0:
            microphones.append(device_info['name'])

    p.terminate()
    return microphones

# Get available output MIDI ports
def get_available_midis():
    ports = []
    for port in mido.get_output_names():
        ports.append(port)
    return ports

# Convert string from frequency selector to extract only the integer value
def str_frequency_to_int(str):
    if str == "24 Hz":
        return 24
    elif str == "25 Hz":
        return 25
    elif str == "30 Hz":
        return 30
    else:
        return 0

# Toggle LTC Listener from button
def toggle_read_ltc():
    enable_listening.set(True) if enable_listening.get() == False else enable_listening.set(False)
    status_color.set("Orange") if enable_listening.get() == True else status_color.set("Red")
    status_square.configure(bg=status_color.get())
    if enable_listening.get():
        toggle_button.configure(text="Disable listener")
        label_microphone.configure(state="disabled")
        label_frequency.configure(state="disabled")
        label_midi.configure(state="disabled")
    else:
        toggle_button.configure(text="Enable listener")
        label_microphone.configure(state="normal")
        label_frequency.configure(state="normal")
        label_midi.configure(state="normal")

    init_ltc_listener()

# Defines values from lists
microphones_options = get_available_microphones()
frequencies_options = ["24 Hz", "25 Hz", "30 Hz"]
midis_options = get_available_midis()

# Create main frame
frame = tk.Tk()
frame.title("SMPTE LTC to MTC 1.0")
frame.geometry("300x300")
frame.resizable(width=False, height=False)

# Define variables from tk
selected_microphone = tk.StringVar(value=microphones_options[0])
selected_frequency = tk.StringVar(value=frequencies_options[0])
selected_midi = tk.StringVar(value=midis_options[0])
selected_microphone_index = tk.IntVar(value=0)
enable_listening = tk.BooleanVar(value=False)
status_color = tk.StringVar(value="Red")

# Configure grid to center elements
for i in range(8):
    frame.grid_rowconfigure(i, weight=1)
    frame.grid_columnconfigure(i, weight=1)

# Draw status square
status_square = tk.Canvas(frame, width=50, height=50, bg="red")
status_square.grid(row=0, column=4, pady=10, sticky="n")

# Draw microphone selector
label_microphone = tk.Label(frame, text="Select microphone", font=("Helvetica", 10, "bold"))
label_microphone.grid(row=1, column=4, pady=5, sticky="n")
label_microphone = tk.OptionMenu(frame, selected_microphone, *microphones_options)
label_microphone.grid(row=2, column=4, pady=5, sticky="n")

# Draw frequency selector
label_frequency = tk.Label(frame, text="Select frequency", font=("Helvetica", 10, "bold"))
label_frequency.grid(row=3, column=4, pady=5, sticky="n")
label_frequency = tk.OptionMenu(frame, selected_frequency, *frequencies_options)
label_frequency.grid(row=4, column=4, pady=5, sticky="n")

# Draw MIDI output selector
label_midi = tk.Label(frame, text="Select MIDI output", font=("Helvetica", 10, "bold"))
label_midi.grid(row=5, column=4, pady=5, sticky="n")
label_midi = tk.OptionMenu(frame, selected_midi, *midis_options)
label_midi.grid(row=6, column=4, pady=5, sticky="n")

# Draw toggle button
toggle_button = tk.Button(frame, text="Enable listener", command=toggle_read_ltc)
toggle_button.grid(row=7, column=4, pady=10, sticky="n")

# Starting main loop
frame.mainloop()