#!/usr/bin/env python3
"""First-time developer setup for The Broken Seal on Windows, then the build.

    py scripts/setup_dev.py

Needs MSYS2 at C:\\msys64 with these packages:
mingw-w64-x86_64-{gcc,make,cmake,ninja,SDL2,zlib}

It makes what build_dev.bat expects to exist, using only your ROM (no
disassembly): builds the translator and the code generator, generates the
game code, configures the build folder and runs build_dev.bat. Finished
steps are skipped when run again. Everything made is ignored by git.
"""
import argparse, hashlib, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME = ROOT / "The Broken Seal"
ENGINE = ROOT / "engine"
SHA1 = "5c4695205413df7db52b9a184815a07783999971"  # USA/Europe
SETUP = GAME / "local" / "setup"
CODE = GAME / "local" / "gs011"
BUILD = GAME / "build" / "gs011_opt"
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""


def stop(message):
    sys.exit(f"\nSetup stopped: {message}")


def run(step, command):
    print(f"\n=== {step} ===", flush=True)
    result = subprocess.run([str(part) for part in command], cwd=ROOT)
    if result.returncode:
        stop(f"'{step}' failed ({result.returncode}). The error is above.")


def find_rom(given):
    target = ROOT / "ROMs" / "The Broken Seal.gba"
    candidates = [pathlib.Path(given)] if given else [target] + sorted((ROOT / "ROMs").rglob("*"))
    for path in candidates:
        if path.is_file() and hashlib.sha1(path.read_bytes()).hexdigest() == SHA1:
            if path.resolve() != target.resolve():
                if target.exists():
                    stop(f"{target} is a different file. Move it aside and run again.")
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(path, target)
                print(f"Copied {path.name} to {target}")
            return target
    stop("no Golden Sun (USA, Europe) ROM found in ROMs/. Unzip it there, or pass --rom.")


def main():
    options = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    options.add_argument("--rom")
    options.add_argument("--mingw", default="C:/msys64/mingw64" if WINDOWS else "/usr")
    options.add_argument("--no-build", action="store_true", help="stop before build_dev.bat")
    a = options.parse_args()

    mingw = pathlib.Path(a.mingw)
    tools = {name: mingw / "bin" / (name + EXE) for name in ("gcc", "g++", "cmake", "ninja")}
    if WINDOWS:
        tools["make"] = mingw / "bin" / "mingw32-make.exe"
    missing = [str(path) for path in tools.values() if not path.is_file()]
    if WINDOWS and not (mingw / "include" / "SDL2" / "SDL.h").is_file():
        missing.append("SDL2")
    if WINDOWS and not (mingw / "include" / "zlib.h").is_file():
        missing.append("zlib")
    if missing:
        stop("missing build tools:\n  " + "\n  ".join(missing) +
             "\nInstall the MSYS2 packages listed at the top of this script.")
    # The build scripts look for python.exe and cmake.exe on PATH.
    os.environ["PATH"] = os.pathsep.join(
        [str(pathlib.Path(sys.executable).parent), str(mingw / "bin"), os.environ["PATH"]])
    rom = find_rom(a.rom)
    cmake = tools["cmake"]
    toolchain = ["-G", "Ninja", f"-DCMAKE_C_COMPILER={tools['gcc'].as_posix()}",
                 f"-DCMAKE_CXX_COMPILER={tools['g++'].as_posix()}",
                 f"-DCMAKE_MAKE_PROGRAM={tools['ninja'].as_posix()}"]

    if not (CODE / "main" / "recompiled.h").is_file():
        translator_build = ENGINE / "build" / "setup"
        run("Configuring the translator",
            [cmake, "-S", ENGINE, "-B", translator_build, "-DCMAKE_BUILD_TYPE=Release", *toolchain])
        run("Building the translator",
            [cmake, "--build", translator_build, "--target", "gba_recompile"])
        translator = translator_build / ("gba_recompile" + EXE)

        generator = SETUP / "bin" / ("gsr_builder" + EXE)
        generator.parent.mkdir(parents=True, exist_ok=True)
        sources = [ROOT / "player_builder" / f"{n}.cpp"
                   for n in ("builder_main", "guest_call", "block_timing")]
        sources += [ENGINE / "src" / "armv4t" / f"{n}.cpp"
                    for n in ("interpreter", "arm_decode", "thumb_decode", "arm_ir")]
        sources.append(ENGINE / "src" / "gba" / "sha1.cpp")
        link = ["-municode", "-static", "-lshell32", "-lole32", "-ladvapi32"] if WINDOWS else ["-pthread"]
        run("Building the code generator",
            [tools["g++"], "-std=c++20", "-O2", "-w", "-I", ENGINE / "src" / "armv4t",
             "-I", ENGINE / "src" / "gba", *sources, "-o", generator, *link])

        # The generator insists on an engine to link against, even when it only
        # generates code. Empty stand-ins satisfy that check.
        stand_in = SETUP / "engine_stand_in"
        for name in ("libGoldenSunRecomp_api.a", "include/runtime_arm.h"):
            (stand_in / name).parent.mkdir(parents=True, exist_ok=True)
            (stand_in / name).touch()
        work = SETUP / "work"
        run("Generating the game code from your ROM",
            [generator, "--generate-only", "--keep-work", "--rom", rom,
             "--data", GAME / "config" / "usa", "--work", work,
             "--recompiler", translator, "--engine", stand_in, "--toolchain", mingw,
             "--jobs", str(max(1, (os.cpu_count() or 4) // 2))])
        if CODE.exists():
            stop(f"{CODE} exists but is incomplete. Delete it and run again.")
        (work / "gen").rename(CODE)

    if not (BUILD / "build.ninja").is_file():
        run("Configuring the game build",
            [cmake, "-S", GAME, "-B", BUILD, "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
             "-DGSR_BUILD_LOCAL_RUNNER=ON",
             f"-DGSR_GENERATED_DIR:PATH={(CODE / 'main').as_posix()}", *toolchain])

    if a.no_build or not WINDOWS:
        print("\nSetup finished. Build with:  .\\build_dev.bat -Game BrokenSeal")
        return
    run("Building the game (this takes a long while)",
        ["cmd", "/c", ROOT / "build_dev.bat", "-Game", "BrokenSeal"])


if __name__ == "__main__":
    main()
