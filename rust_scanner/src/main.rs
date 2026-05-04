use serde::Serialize;
use std::env;
use std::fs::{self, ReadDir};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

#[derive(Serialize)]
#[serde(tag = "event", rename_all = "snake_case")]
enum Event<'a> {
    Add {
        path: &'a str,
        name: &'a str,
        is_dir: bool,
        size: Option<u64>,
        modified: f64,
    },
    UpdateSize {
        path: &'a str,
        size: u64,
    },
    Done,
}

struct Frame {
    path: PathBuf,
    name: String,
    iter: ReadDir,
    total: u64,
    modified: f64,
    emit_folder: bool,
}

struct Args {
    root: PathBuf,
    quick: bool,
    skip_dirs: Vec<String>,
}

fn main() {
    let args = match parse_args() {
        Ok(args) => args,
        Err(message) => {
            eprintln!("{message}");
            std::process::exit(2);
        }
    };

    let stdout = io::stdout();
    let mut out = BufWriter::new(stdout.lock());
    let _ = scan(&args.root, args.quick, &args.skip_dirs, &mut out);
    let _ = write_event(&mut out, &Event::Done);
    let _ = out.flush();
}

fn parse_args() -> Result<Args, String> {
    let mut root: Option<PathBuf> = None;
    let mut quick = true;
    let mut skip_dirs: Vec<String> = Vec::new();

    let mut it = env::args().skip(1);
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--root" => {
                let value = it.next().ok_or("--root requires a path")?;
                root = Some(PathBuf::from(value));
            }
            "--quick" => quick = true,
            "--full" => quick = false,
            "--skip" => {
                if let Some(value) = it.next() {
                    skip_dirs.extend(
                        value
                            .split(';')
                            .map(|s| s.trim().to_ascii_lowercase())
                            .filter(|s| !s.is_empty()),
                    );
                }
            }
            _ => {
                if root.is_none() {
                    root = Some(PathBuf::from(arg));
                }
            }
        }
    }

    let root = root.ok_or("usage: scanner_rs --root <path> [--quick|--full] [--skip name;name]")?;
    Ok(Args { root, quick, skip_dirs })
}

fn scan<W: Write>(root: &Path, quick: bool, skip_dirs: &[String], out: &mut W) -> io::Result<()> {
    let root_iter = match fs::read_dir(root) {
        Ok(iter) => iter,
        Err(_) => return Ok(()),
    };

    let root_name = root
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| root.to_string_lossy().to_string());

    let mut stack = vec![Frame {
        path: root.to_path_buf(),
        name: root_name,
        iter: root_iter,
        total: 0,
        modified: 0.0,
        emit_folder: false,
    }];

    let mut emitted = 0usize;

    while let Some(frame) = stack.last_mut() {
        let entry = match frame.iter.next() {
            Some(Ok(entry)) => entry,
            Some(Err(_)) => continue,
            None => {
                let completed = stack.pop().expect("frame exists");
                let folder_size = completed.total;

                if completed.emit_folder {
                    let path_string = path_to_string(&completed.path);
                    if quick {
                        write_event(out, &Event::UpdateSize { path: &path_string, size: folder_size })?;
                    } else {
                        write_event(
                            out,
                            &Event::Add {
                                path: &path_string,
                                name: &completed.name,
                                is_dir: true,
                                size: Some(folder_size),
                                modified: completed.modified,
                            },
                        )?;
                    }
                    emitted += 1;
                }

                if let Some(parent) = stack.last_mut() {
                    parent.total = parent.total.saturating_add(folder_size);
                }

                if emitted >= 256 {
                    out.flush()?;
                    emitted = 0;
                }
                continue;
            }
        };

        let name = entry.file_name().to_string_lossy().to_string();
        let path = entry.path();
        let metadata = match entry.metadata() {
            Ok(metadata) => metadata,
            Err(_) => continue,
        };
        let modified = modified_seconds(&metadata);

        if metadata.is_dir() {
            if should_skip_dir(&name, skip_dirs) {
                continue;
            }

            let path_string = path_to_string(&path);
            if quick {
                write_event(
                    out,
                    &Event::Add {
                        path: &path_string,
                        name: &name,
                        is_dir: true,
                        size: None,
                        modified,
                    },
                )?;
                emitted += 1;
            }

            match fs::read_dir(&path) {
                Ok(child_iter) => stack.push(Frame {
                    path,
                    name,
                    iter: child_iter,
                    total: 0,
                    modified,
                    emit_folder: true,
                }),
                Err(_) => {
                    if quick {
                        write_event(out, &Event::UpdateSize { path: &path_string, size: 0 })?;
                    } else {
                        write_event(
                            out,
                            &Event::Add {
                                path: &path_string,
                                name: &name,
                                is_dir: true,
                                size: Some(0),
                                modified,
                            },
                        )?;
                    }
                    emitted += 1;
                }
            }
        } else if metadata.is_file() {
            let size = metadata.len();
            frame.total = frame.total.saturating_add(size);
            let path_string = path_to_string(&path);
            write_event(
                out,
                &Event::Add {
                    path: &path_string,
                    name: &name,
                    is_dir: false,
                    size: Some(size),
                    modified,
                },
            )?;
            emitted += 1;
        }

        if emitted >= 256 {
            out.flush()?;
            emitted = 0;
        }
    }

    Ok(())
}

fn should_skip_dir(name: &str, skip_dirs: &[String]) -> bool {
    let lower = name.to_ascii_lowercase();
    skip_dirs.iter().any(|skip| skip == &lower)
}

fn modified_seconds(metadata: &fs::Metadata) -> f64 {
    metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|duration| duration.as_secs_f64())
        .unwrap_or(0.0)
}

fn path_to_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn write_event<W: Write>(out: &mut W, event: &Event<'_>) -> io::Result<()> {
    serde_json::to_writer(&mut *out, event)?;
    out.write_all(b"\n")
}
