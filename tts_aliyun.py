import time
import threading
import sys
import nls
import os
import ssl
import json
from nls.token import getToken

#1、带字幕的语音合成方案。
#2、基于阿里云TTS服务。

# 全局设置：禁用证书验证
# ssl._create_default_https_context = ssl._create_unverified_context

URL = "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1"
#ACCESS_AKID = "your access id"
#ACCESS_AKKEY = "your access key"
#TOKEN = getToken(ACCESS_AKID, ACCESS_AKKEY)
TOKEN = "your token" #临时用的，在阿里云后台生成，长期使用请使用getToken。
APPKEY = "your app key"

def format_timestamp(milliseconds):
    """将毫秒转换为 VTT/SRT 格式的时间戳"""
    hours = int(milliseconds) // (3600 * 1000)
    minutes = (int(milliseconds) % (3600 * 1000)) // (60 * 1000)
    seconds = (int(milliseconds) % (60 * 1000)) // 1000
    ms = int(milliseconds) % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"

def write_srt(file_path, subtitle_entries):
    """写入SRT格式字幕文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        for i, entry in enumerate(subtitle_entries, 1):
            if entry['text'].strip():
                print(f"写入SRT字幕: {entry}")
                start_time = float(entry['start'])
                end_time = float(entry['end'])
                f.write(f"{i}\n")
                f.write(f"{format_timestamp(start_time).replace('.', ',')} --> {format_timestamp(end_time).replace('.', ',')}\n")
                f.write(f"{entry['text']}\n\n")

def split_sentences(text: str) -> list:
    """将文本分割成句子"""
    # 定义分隔符
    delimiters = ['。', '！', '？', '!', '?', '.', '\n']
    
    sentences = []
    current = []
    
    for char in text:
        current.append(char)
        if char in delimiters:
            sentence = ''.join(current).strip()
            if sentence:  # 忽略空句子
                sentences.append(sentence)
            current = []
    
    # 处理最后一个句子
    if current:
        sentence = ''.join(current).strip()
        if sentence:
            sentences.append(sentence)
    
    return sentences

class TestTts:
    def __init__(self, tid, audio_file, text):
        self.__th = threading.Thread(target=self.__test_run)
        self.__id = tid
        self.__audio_file = audio_file
        self.__text = text
        self.finished = False
        self.subtitle_entries = []
        self.current_time = 0
   
    def start(self):
        self.__f = open(self.__audio_file, "wb")
        self.__th.start()
    
    def join(self):
        self.__th.join()
    
    def test_on_metainfo(self, message, *args):
        pass

    def test_on_error(self, message, *args):
        print(f"{self.__id} 错误: {message}")
        self.finished = True

    def test_on_close(self, *args):
        try:
            if not self.__f.closed:
                self.__f.flush()
                self.__f.close()
        except Exception as e:
            print(f"{self.__id} 关闭文件失败: {e}")
        self.finished = True

    def test_on_data(self, data, *args):
        try:
            self.__f.write(data)
        except Exception as e:
            print(f"{self.__id} 写入失败: {e}")

    def test_on_completed(self, message, *args):
        try:
            self.__f.flush()
            self.__f.close()
        except Exception as e:
            print(f"{self.__id} 完成处理时出错: {e}")
        self.finished = True

    def generate_subtitles(self):
        if self.subtitle_entries:
            srt_file = self.__audio_file.rsplit('.', 1)[0] + '.srt'
            write_srt(srt_file, self.subtitle_entries)
            print(f"{self.__id} 字幕文件已生成: {srt_file}")

    def __test_run(self):
        try:
            use_long_tts = len(self.__text) > 300
            
            # 分割文本为句子
            sentences = split_sentences(self.__text)
            current_time = 0
            
            # 创建合成器实例
            tts = nls.NlsSpeechSynthesizer(
                url=URL,
                token=TOKEN,
                appkey=APPKEY,
                long_tts=use_long_tts,
                on_metainfo=self.test_on_metainfo,
                on_data=self.test_on_data,
                on_completed=self.test_on_completed,
                on_error=self.test_on_error,
                on_close=self.test_on_close,
                callback_args=[self.__id]
            )

            # 开始合成
            r = tts.start(
                self.__text,
                voice="xiaoyun",
                aformat="wav",
                sample_rate=16000,
                volume=50,
                speech_rate=0,
                pitch_rate=0
            )
            
            # 生成字幕
            for i, sentence in enumerate(sentences):
                # 估算句子时长
                duration = 0
                for char in sentence:
                    if '\u4e00' <= char <= '\u9fff':  # 中文字符
                        duration += 300
                    elif char.isalpha():  # 英文字符
                        duration += 200
                    else:  # 其他字符
                        duration += 100
                
                # 添加字幕条目
                entry = {
                    'start': current_time,
                    'end': current_time + duration,
                    'text': sentence
                }
                self.subtitle_entries.append(entry)
                current_time += duration + 500  # 句子间添加500ms间隔
            
            # 等待合成完成
            while not self.finished:
                time.sleep(0.1)
            
            # 生成字幕文件
            self.generate_subtitles()
            
        except Exception as e:
            print(f"{self.__id} 处理出错: {e}")
            self.finished = True

def process_folder(input_folder, output_folder):
    """处理文件夹中的所有文本文件"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    txt_files = [f for f in os.listdir(input_folder) if f.endswith('.txt')]
    active_threads = []
    
    print(f"找到 {len(txt_files)} 个文本文件")
    
    # 限制并发线程数
    max_concurrent_threads = 3
    
    for i, txt_file in enumerate(txt_files):
        input_path = os.path.join(input_folder, txt_file)
        output_path = os.path.join(output_folder, txt_file.replace('.txt', '.wav'))
        
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()
            
            if not text:
                print(f"跳过空文件: {txt_file}")
                continue
                
            print(f"正在处理: {txt_file}")
            thread_name = f"tts_thread_{i}"
            
            tts_thread = TestTts(thread_name, output_path, text)
            active_threads.append(tts_thread)
            tts_thread.start()
            
            if len(active_threads) >= max_concurrent_threads:
                for t in active_threads:
                    t.join()
                active_threads = []
                time.sleep(1)
                
        except Exception as e:
            print(f"处理文件 {txt_file} 时出错: {e}")
    
    # 等待剩余的线程完成
    for t in active_threads:
        t.join()
    
    print("所有文件处理完成")

if __name__ == '__main__':
    # 处理文件夹
    input_folder = "input"
    output_folder = "output"
    process_folder(input_folder, output_folder)
