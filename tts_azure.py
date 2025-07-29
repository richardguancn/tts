import azure.cognitiveservices.speech as speechsdk
import asyncio
import os

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

def write_vtt(file_path, subtitle_entries):
    """写入VTT格式字幕文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        # VTT文件头
        f.write("WEBVTT\n\n")
        
        for i, entry in enumerate(subtitle_entries, 1):
            if entry['text'].strip():
                print(f"写入VTT字幕: {entry}")
                start_time = float(entry['start'])
                end_time = float(entry['end'])
                f.write(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n")
                f.write(f"{entry['text']}\n\n")

def split_text(text: str) -> list:
    """按标点符号和换行符分割中英混合文本为字幕片段"""
    # 定义中英文标点符号
    cn_delimiters = ['。', '！', '？', '，', '、', '；', '：']  # 中文标点
    en_delimiters = ['.', '!', '?', ',', ';', ':']  # 英文标点
    delimiters = cn_delimiters + en_delimiters
    
    # 首先按换行符分割
    paragraphs = text.split('\n')
    segments = []
    
    for paragraph in paragraphs:
        if not paragraph.strip():
            continue
            
        current_segment = ""
        # 遍历段落中的每个字符
        for i, char in enumerate(paragraph):
            current_segment += char
            
            # 当遇到分隔符时创建新片段
            if char in delimiters:
                # 检查是否需要保留当前分隔符和下一个空格
                next_char = paragraph[i+1] if i+1 < len(paragraph) else ''
                
                # 如果是英文句子，保留标点和后面的空格
                if char in en_delimiters and next_char == ' ':
                    current_segment += next_char
                
                if current_segment.strip():
                    segments.append(current_segment.strip())
                current_segment = ""
                continue
            
            # 处理英文单词之间的空格
            if char == ' ':
                # 检查前后是否都是英文
                prev_char = current_segment[-1] if current_segment else ''
                next_char = paragraph[i+1] if i+1 < len(paragraph) else ''
                
                if (prev_char.isalpha() and next_char.isalpha()) or \
                   (prev_char.isdigit() and next_char.isdigit()):
                    current_segment += char
        
        # 处理段落的最后一部分
        if current_segment.strip():
            segments.append(current_segment.strip())
            
        # 在每个非空段落后添加换行标记
        if segments and not segments[-1].endswith('\n'):
            segments[-1] = segments[-1] + '\n'
    
    # 清理空段落并去除首尾空白
    segments = [s.strip() for s in segments if s.strip()]
    
    return segments

def is_chinese(text: str) -> bool:
    """判断文本是否包含中文"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

def generate_ssml(text: str, voice: str, sentences: list) -> str:
    """生成带有语言切换和停顿的SSML"""
    # 判断主要语音是中文还是英文
    is_main_chinese = 'zh-CN' in voice
    
    ssml_parts = []
    for i, s in enumerate(sentences):
        if s.strip():
            # 判断当前句子的语言
            is_sentence_chinese = is_chinese(s)
            
            # 如果是英文句子，使用较慢的语速
            rate = "1.1" if is_sentence_chinese else "0.9"
            
            # 如果句子语言与主语音不同，添加语言标记
            if is_sentence_chinese != is_main_chinese:
                lang_tag = 'zh-CN' if is_sentence_chinese else 'en-US'
                ssml_parts.append(
                    f'<bookmark mark="subtitle_{i}"/><prosody rate="{rate}"><lang xml:lang="{lang_tag}">{s}</lang></prosody><break time="400ms"/>'
                )
            else:
                ssml_parts.append(f'<bookmark mark="subtitle_{i}"/><prosody rate="{rate}">{s}</prosody><break time="400ms"/>')
    
    ssml = f"""
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{'zh-CN' if is_main_chinese else 'en-US'}">
        <voice name="{voice}">
            {' '.join(ssml_parts)}
        </voice>
    </speak>
    """
    return ssml

def clean_text(text: str) -> str:
    """更严格的文本清理，处理编码和特殊字符问题"""
    try:
        # 基本替换字典
        replacements = {
            '"': '"',
            '"': '"',
            ''': "'",
            ''': "'",
            '…': '...',
            '–': '-',
            '—': '-',
            '\u200b': '',  # 零宽空格
            '\ufeff': '',  # BOM
            '\r': '\n',    # 统一换行符
            '\t': ' ',     # 替换制表符
        }
        
        # 第一步：替换已知的特殊字符
        cleaned_text = text
        for old, new in replacements.items():
            cleaned_text = cleaned_text.replace(old, new)
        
        # 第二步：移除控制字符，但保留换行符
        cleaned_text = ''.join(char for char in cleaned_text 
                             if char == '\n' or (char.isprintable() and ord(char) < 65536))
        
        # 第三步：处理多余的空白
        lines = cleaned_text.split('\n')
        cleaned_lines = [line.strip() for line in lines]
        cleaned_text = '\n'.join(line for line in cleaned_lines if line)
        
        # 第四步：确保文本是有效的UTF-8
        cleaned_text = cleaned_text.encode('utf-8', errors='ignore').decode('utf-8')
        
        return cleaned_text
        
    except Exception as e:
        print(f"文本清理过程中出错: {str(e)}")
        # 返回一个安全的默认值
        return "Text cleaning error occurred."

async def run_tts(text: str, output: str, voice: str ='zh-CN-XiaoxiaoMultilingualNeural') -> None:
    try:
        # 确保输入文本不为空
        if not text or not text.strip():
            raise ValueError("输入文本为空")
            
        # 清理输入文本
        cleaned_text = clean_text(text)
        if not cleaned_text or cleaned_text == "Text cleaning error occurred.":
            raise ValueError("文本清理失败")
            
        # 检查文件路径
        output_dir = os.path.dirname(output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        baseDir = './'
        password = 'your password'
        speech_config = speechsdk.SpeechConfig(subscription=password, region="eastasia")
        file_config = speechsdk.audio.AudioOutputConfig(filename=output)

        speech_config.speech_synthesis_voice_name = voice
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_RequestSentenceBoundary, "true")

        # 创建合成器
        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=file_config)
        
        # 存储字幕信息
        subtitle_entries = []
        sentences = split_text(cleaned_text)
        
        if not sentences:
            raise ValueError("文本分割后为空")
            
        current_sentence_index = 0
        total_duration = 0

        def handle_bookmark(evt):
            nonlocal subtitle_entries, current_sentence_index, total_duration
            try:
                print(f"收到书签事件: {evt.text}")
                if evt.text.startswith("subtitle_"):
                    offset = float(evt.audio_offset) / 10000
                    
                    # 减小字幕间隔
                    if subtitle_entries:
                        subtitle_entries[-1]['end'] = offset - 300  # 提前结束300ms
                    
                    if current_sentence_index < len(sentences):
                        entry = {
                            'start': offset + 100,  # 延迟开始100ms
                            'end': offset + 5000,
                            'text': sentences[current_sentence_index]
                        }
                        subtitle_entries.append(entry)
                        print(f"添加字幕条目: {entry}")
                        current_sentence_index += 1
                        total_duration = max(total_duration, offset + 5000)
                    
            except Exception as e:
                print(f"处理书签事件时出错: {e}")

        speech_synthesizer.bookmark_reached.connect(handle_bookmark)
        
        print("开始语音合成...")
        
        # 使用清理后的文本生成SSML
        ssml = generate_ssml(cleaned_text, voice, sentences)
        print(f"生成的SSML:\n{ssml}")

        # 修改错误处理部分
        try:
            speech_synthesis_result = speech_synthesizer.speak_ssml_async(ssml).get()
            
            if speech_synthesis_result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
                print(f"语音合成未完成，状态: {speech_synthesis_result.reason}")
                return
                
            print(f"语音合成结果: {speech_synthesis_result}")

            if subtitle_entries:
                last_end_time = total_duration
                subtitle_entries[-1]['end'] = last_end_time
                print(f"设置最后一个字幕的结束时间: {last_end_time}ms")

            # 生成SRT文件
            srt_file = output.rsplit('.', 1)[0] + '.srt'
            write_srt(srt_file, subtitle_entries)
            print(f"SRT字幕文件已生成: {srt_file}")
            
            # 生成VTT文件
            vtt_file = output.rsplit('.', 1)[0] + '.vtt'
            write_vtt(vtt_file, subtitle_entries)
            print(f"VTT字幕文件已生成: {vtt_file}")
            
        except Exception as synth_error:
            print(f"语音合成过程中出错: {str(synth_error)}")
            if hasattr(speech_synthesis_result, 'properties'):
                print(f"合成属性: {speech_synthesis_result.properties}")
            raise

    except Exception as e:
        print(f"发生错误: {str(e)}")
        print(f"错误类型: {type(e)}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        raise

if __name__ == '__main__':
    try:
        test_text = """她总是保持着非常positive的态度，无论遇到什么困难，都能keep calm and carry on。
学习英语的时候，我意识到practice makes perfect，所以我总是try my best去多练习。
我们计划了一个road trip，沿途可以stop by一些著名的景点，比如the Great Wall。”"""
        
        # 确保输出目录存在
        output_file = 'test.mp3'
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        print(f"测试文本: {test_text}")
        asyncio.run(run_tts(test_text, output_file, 'zh-CN-XiaoxiaoMultilingualNeural'))
        
    except Exception as e:
        print(f"主程序错误: {str(e)}")
