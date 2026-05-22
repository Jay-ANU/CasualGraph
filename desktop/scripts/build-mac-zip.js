const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const distDir = path.join(root, "dist");
const appName = "CausalGraph Pet.app";
const appDir = path.join(distDir, "mac-arm64", appName);
const zipPath = path.join(distDir, "CausalGraph-Pet-0.1.0-mac-arm64.zip");
const verifyDir = path.join(distDir, ".verify-mac-zip");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    env: { ...process.env, ...options.env },
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} exited with ${result.status}`);
  }
}

function localBin(name) {
  return path.join(root, "node_modules", ".bin", process.platform === "win32" ? `${name}.cmd` : name);
}

if (process.platform !== "darwin") {
  throw new Error("dist:mac must be run on macOS so codesign and ditto can validate the app bundle.");
}

fs.rmSync(path.join(distDir, "mac-arm64"), { recursive: true, force: true });
fs.rmSync(zipPath, { force: true });
fs.rmSync(`${zipPath}.blockmap`, { force: true });
fs.rmSync(verifyDir, { recursive: true, force: true });

run(localBin("electron-builder"), ["--mac", "dir", "--arm64"], {
  env: { CSC_IDENTITY_AUTO_DISCOVERY: "false" },
});

if (!fs.existsSync(appDir)) {
  throw new Error(`Expected app bundle was not generated: ${appDir}`);
}

run("codesign", ["--force", "--deep", "--sign", "-", appDir]);
run("codesign", ["--verify", "--deep", "--strict", "--verbose=4", appDir]);

run("ditto", ["-c", "-k", "--sequesterRsrc", "--keepParent", appDir, zipPath]);

fs.mkdirSync(verifyDir, { recursive: true });
run("ditto", ["-x", "-k", zipPath, verifyDir]);
run("codesign", ["--verify", "--deep", "--strict", "--verbose=4", path.join(verifyDir, appName)]);
fs.rmSync(verifyDir, { recursive: true, force: true });

console.log(`Created signed macOS zip: ${zipPath}`);
