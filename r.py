from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto 
from pyrogram import Client, filters
import asyncio
import subprocess
import uuid, json, os, shutil
from presets import FP
from presets import cmdrunok, Vduration

async def take_screenshots_batch(input_path, times_in_seconds):
    try:
        if not times_in_seconds:
            return []

        # Create temporary output directory
        temp_dir = f"temp_{uuid.uuid4().hex}"
        os.makedirs(temp_dir, exist_ok=True)

        # Build filter complex for multiple timestamps
        filter_str = "select='" + "+".join(
            [f"eq(t\,{ts})" for ts in times_in_seconds]
        ) + "',thumbnail=100:1"

        command = [
            'ffmpeg',
            '-y',  # Overwrite files
            '-hide_banner',
            '-loglevel', 'error',
            '-i', input_path,
            '-vf', filter_str,
            '-vsync', 'vfr',  # Variable frame rate
            '-q:v', '2',
            f'{temp_dir}/output_%03d.jpg'
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"FFmpeg error: {stderr.decode()}")
            return []

        # Collect and rename generated files
        generated_files = sorted(glob.glob(f"{temp_dir}/output_*.jpg"))
        screenshots = []
        for idx, file_path in enumerate(generated_files):
            new_name = f"{uuid.uuid4().hex}.jpg"
            os.rename(file_path, new_name)
            screenshots.append((new_name, times_in_seconds[idx]))
            
        # Cleanup temporary directory
        shutil.rmtree(temp_dir)
        return screenshots

    except Exception as e:
        print(f"Batch screenshot error: {str(e)}")
        return []

async def GETcustomss(c, m, msg, msg_id, input_path):
    screenshots = []
    try:
        duration = await Vduration(input_path)
        if not duration:
            await msg.edit("❌ Failed to get video duration")
            return

        await msg.edit(
            f"**⏳ Provide timestamps (comma-separated)**\n"
            f"Max duration: {int(duration//3600):02}:{int((duration%3600)//60):02}:{int(duration%60):02}\n"
            "Formats accepted: 00:01:23 [hh:mm:ss], 01:23 [mm:ss], or 45 [ss]"
        )

        try:
            ask_msg = await c.listen(
                chat_id=m.chat.id,
                user_id=m.from_user.id,
                filters=filters.text,
                timeout=120
            )
        except asyncio.TimeoutError:
            await msg.edit("⌛ Timed out after 2 minutes")
            return
            
        valid_times = []
        invalid_entries = []
        raw_input = ask_msg.text.replace("，", ",")
        
        for entry in raw_input.split(","):
            entry = entry.strip()
            try:
                parts = list(map(int, entry.split(":")))
                if len(parts) == 3:
                    h, m, s = parts
                elif len(parts) == 2:
                    h, m, s = 0, *parts
                elif len(parts) == 1:
                    h, m, s = 0, 0, parts[0]
                else:
                    raise ValueError
                    
                total_seconds = h * 3600 + m * 60 + s
                if total_seconds > duration:
                    invalid_entries.append(f"{entry} (exceeds duration)")
                else:
                    valid_times.append({
                        "formatted": f"{h:02}:{m:02}:{s:02}",
                        "seconds": total_seconds
                    })
                    
            except Exception:
                invalid_entries.append(entry)

        if not valid_times:
            await msg.edit("❌ No valid timestamps provided")
            return

        # Generate screenshots in one batch
        times_in_seconds = [t["seconds"] for t in valid_times]
        formatted_times = [t["formatted"] for t in valid_times]
        
        results = await take_screenshots_batch(input_path, times_in_seconds)
        
        # Verify results
        success_count = 0
        output_files = []
        for idx, (filename, timestamp) in enumerate(results):
            try:
                time_str = formatted_times[idx]
                output_files.append((filename, time_str))
                success_count += 1
            except IndexError:
                pass  # Handle potential mismatches

        # Send media in batches of 10
        for batch in chunked(output_files, 10):
            media_group = [
                InputMediaPhoto(media=open(f[0], 'rb'), caption=f"🕒 {f[1]}")
                for f in batch
            ]
            await c.send_media_group(m.chat.id, media_group)

        # Final status message
        status = f"✅ Generated {success_count}/{len(valid_times)} screenshots"
        if invalid_entries:
            status += f"\n⚠️ Invalid entries: {', '.join(invalid_entries[:3])}"
            if len(invalid_entries) > 3:
                status += f" (+{len(invalid_entries)-3} more)"
        
        await msg.edit(status)

    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)[:200]}")
        print(f"CustomSS Error: {str(e)}")
    finally:
        for f, _ in screenshots:
            try:
                os.remove(f)
            except:
                pass

@Client.on_callback_query(filters.regex(r"^randss:(\d+):(\d+)$"))
async def randomSs(c, cb):
    try:
        num = int(cb.data.split(":")[1])
        id = int(cb.data.split(":")[2])
        
        if id not in FP:
            await cb.message.edit("❌ Session expired")
            return

        input_path = FP[id]
        duration = await Vduration(input_path)
        if not duration:
            await cb.message.edit("❌ Failed to get video duration")
            return

        # Generate random timestamps
        import random
        max_time = int(duration - 1)
        if max_time < 1:
            await cb.message.edit("❌ Video too short for screenshots")
            return

        random_seconds = sorted(random.sample(range(1, max_time), min(num, max_time-1)))
        if not random_seconds:
            await cb.message.edit("❌ Couldn't generate valid timestamps")
            return

        # Generate all screenshots in one batch
        results = await take_screenshots_batch(input_path, random_seconds)
        
        # Process results
        success_count = 0
        output_files = []
        for idx, (filename, timestamp) in enumerate(results):
            try:
                # Convert seconds to HH:MM:SS
                h = timestamp // 3600
                m = (timestamp % 3600) // 60
                s = timestamp % 60
                time_str = f"{h:02}:{m:02}:{s:02}"
                output_files.append((filename, time_str))
                success_count += 1
            except Exception as e:
                print(f"Error processing screenshot: {str(e)}")

        # Send media in batches of 10
        for batch in chunked(output_files, 10):
            media_group = [
                InputMediaPhoto(media=open(f[0], 'rb'), caption=f"🕒 {f[1]}")
                for f in batch
            ]
            await c.send_media_group(chat_id=cb.message.chat.id, media=media_group)

        # Update status
        status = f"✅ Generated {success_count}/{num} random screenshots"
        if success_count < num:
            status += f"\n⚠️ Failed to generate {num-success_count} shots"
        await cb.message.edit(status)

    except Exception as e:
        await cb.message.edit(f"❌ Error: {str(e)[:200]}")
        print(f"RandomSS Error: {str(e)}")
    finally:
        # Cleanup files
        for f, _ in output_files:
            try:
                os.remove(f)
            except:
                pass

def chunked(lst, n):
    """Split list into chunks of size n"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]