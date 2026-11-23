// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace CANNBot.Setup {
    public sealed class ProgressTrack : Control {
        public ProgressBarStyle Style = ProgressBarStyle.Marquee;
        public int Value;
        int position;
        public ProgressTrack() {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer, true);
            AccessibleRole = AccessibleRole.ProgressBar;
            TabStop = false;
        }
        public void Advance() { position = (position + 18) % Math.Max(1, Width + 110); Invalidate(); }
        protected override void OnPaint(PaintEventArgs args) {
            args.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using (var path = new GraphicsPath()) {
                float radius = Height - 1;
                path.AddArc(0, 0, radius, radius, 90, 180);
                path.AddArc(Width - radius - 1, 0, radius, radius, 270, 180);
                path.CloseFigure();
                using (var background = new SolidBrush(Color.FromArgb(237, 229, 231))) args.Graphics.FillPath(background, path);
                args.Graphics.SetClip(path);
                using (var foreground = new SolidBrush(Color.FromArgb(146, 31, 47))) {
                    if (Style == ProgressBarStyle.Marquee) args.Graphics.FillRectangle(foreground, position - 110, 0, 110, Height);
                    else args.Graphics.FillRectangle(foreground, 0, 0, Width * Value / 100F, Height);
                }
            }
        }
    }
    // Runs on the UI thread; the worker owns installation and stdout is drained
    // asynchronously. Slow network/installer processes never block the form.
    public sealed class SetupWindow : Form {
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr handle, int command);
        readonly Color red = Color.FromArgb(146, 31, 47);
        readonly Color ink = Color.FromArgb(32, 35, 42);
        readonly Color muted = Color.FromArgb(111, 116, 125);
        readonly string installer, packageRoot, runRoot, statePath;
        readonly Label heading, description, metric, elapsed, stage;
        readonly Label[] steps = new Label[5];
        readonly ProgressTrack progress;
        readonly Button primary, secondary, details;
        readonly TextBox log;
        readonly Timer timer;
        readonly ConcurrentQueue<string> lines = new ConcurrentQueue<string>();
        readonly Stopwatch watch = new Stopwatch();
        Process worker;
        StreamWriter logWriter;
        string phase = "", executable = "", lastState = "";
        bool busy, succeeded, cancelRequested;
        Panel disclosure;
        CheckBox accepted;
        public int Result = 1;

        public SetupWindow(string script, string package, string folder) {
            installer = script; packageRoot = package; runRoot = folder;
            statePath = Path.Combine(runRoot, "progress.json");
            Font = new Font("Microsoft YaHei UI", 9F);
            AutoScaleMode = AutoScaleMode.Font;
            Text = "CANNBot 安装";
            ClientSize = new Size(760, 475);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.White;
            Icon = new Icon(Path.Combine(Path.GetDirectoryName(installer), "setup-icon.ico"));
            FormClosed += delegate { Icon.Dispose(); };

            Panel brand = new Panel { Bounds = new Rectangle(0, 0, 228, 475), BackColor = Color.FromArgb(248, 246, 246) };
            Controls.Add(brand);
            var logo = new PictureBox { Bounds = new Rectangle(28, 32, 44, 44), SizeMode = PictureBoxSizeMode.Zoom, Image = Image.FromFile(Path.Combine(Path.GetDirectoryName(installer), "setup-logo.png")) };
            brand.Controls.Add(logo);
            FormClosed += delegate { logo.Image.Dispose(); };
            Label name = LabelAt(brand, "CANNBot", 82, 32, 138, 30, 16, true); name.ForeColor = red;
            LabelAt(brand, "昇腾 / CANN 开发", 82, 65, 140, 23, 9, false).ForeColor = muted;
            string[] labels = { "检查环境", "下载宿主程序", "安装宿主程序", "准备运行环境", "安装 CANNBot" };
            for (int i = 0; i < steps.Length; i++) {
                steps[i] = LabelAt(brand, (i + 1).ToString("00") + "   " + labels[i], 28, 139 + i * 48, 194, 34, 9, false);
                steps[i].ForeColor = muted;
            }
            LabelAt(brand, "昇腾开发 · 本地与远程工作区", 28, 420, 190, 30, 8, false).ForeColor = muted;

            stage = LabelAt(this, "准备就绪", 264, 38, 450, 24, 9, true); stage.ForeColor = red;
            heading = LabelAt(this, "让 CANNBot 准备就绪", 264, 78, 460, 45, 21, true);
            description = LabelAt(this, "将安装 CANNBot 昇腾开发工作台及所需宿主。\n已有安装会自动复用，请先保存正在进行的操作。", 266, 143, 450, 68, 10, false);
            description.ForeColor = muted;
            metric = LabelAt(this, "即将开始", 266, 241, 450, 30, 11, true);
            progress = new ProgressTrack { Bounds = new Rectangle(268, 287, 450, 10) };
            Controls.Add(progress);
            elapsed = LabelAt(this, "", 266, 310, 450, 28, 9, false); elapsed.ForeColor = muted;
            Panel divider = new Panel { Bounds = new Rectangle(264, 382, 456, 1), BackColor = Color.FromArgb(233, 234, 237) }; Controls.Add(divider);
            details = ButtonAt("查看日志", 264, 411, 96, false);
            secondary = ButtonAt("关闭", 476, 411, 100, false);
            primary = ButtonAt("开始安装", 590, 411, 130, true);
            log = new TextBox { Bounds = new Rectangle(28, 487, 692, 185), Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false, Font = new Font("Consolas", 9F), BackColor = Color.FromArgb(248, 249, 251), BorderStyle = BorderStyle.FixedSingle, Visible = false };
            Controls.Add(log);
            details.Click += delegate {
                log.Visible = !log.Visible;
                ClientSize = new Size(ClientSize.Width, log.Visible ? log.Bottom + ScaleY(24) : secondary.Bottom + ScaleY(26));
                details.Text = log.Visible ? "收起日志" : "查看日志";
            };
            secondary.Click += delegate { Close(); };
            primary.Click += delegate {
                if (busy) { CancelDownload(); return; }
                if (succeeded) {
                    try { Process.Start(new ProcessStartInfo(executable) { UseShellExecute = true }); Close(); }
                    catch (Exception error) { MessageBox.Show(this, "无法打开工作台：" + error.Message, "CANNBot", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
                } else { StartInstall(); }
            };
            FormClosing += delegate(object sender, FormClosingEventArgs args) {
                if (!busy) return;
                args.Cancel = true;
                if (phase == "download") CancelDownload();
                else MessageBox.Show(this, "正在安装，请等待当前操作完成后关闭窗口。", "安装进行中", MessageBoxButtons.OK, MessageBoxIcon.Information);
            };
            timer = new Timer { Interval = 150 };
            timer.Tick += delegate { RefreshInstall(); };
            BuildDisclosure();
            Shown += delegate { ShowWindow(Handle, 5); Activate(); };
        }

        void BuildDisclosure() {
            var policy = new JavaScriptSerializer().Deserialize<Dictionary<string, string>>(File.ReadAllText(Path.Combine(packageRoot, "release-policy.json"), Encoding.UTF8));
            disclosure = new Panel { Bounds = new Rectangle(256, 28, 474, 348), BackColor = Color.White, AutoScroll = true };
            Controls.Add(disclosure); disclosure.BringToFront();
            LabelAt(disclosure, "安装前请阅读", 8, 6, 450, 34, 18, true);
            LabelAt(disclosure, "从官方地址下载 DeepSeek Harness（权利人：DeepSeek，MIT 许可证）。请自行完成官方安装向导中的协议确认。", 8, 48, 445, 52, 9, false);
            AddDisclosureLink(policy, "hostSourceUrl", "宿主来源", 8, 103);
            AddDisclosureLink(policy, "hostLicenseUrl", "MIT 许可", 118, 103);
            AddDisclosureLink(policy, "hostTermsUrl", "宿主用户协议", 228, 103);
            AddDisclosureLink(policy, "hostPrivacyUrl", "宿主隐私政策", 338, 103);
            AddDisclosureLink(policy, "userAgreementUrl", "CANNBot 用户协议", 8, 134);
            AddDisclosureLink(policy, "privacyPolicyUrl", "CANNBot 隐私政策", 228, 134);
            LabelAt(disclosure, "模型输入会发送给您选择的模型服务商。向服务器同步模型账号授权默认关闭，需另行同意。依赖从 npmjs.org 或 npmmirror.com 获取。", 8, 171, 445, 62, 9, false);
            var notices = new LinkLabel { Text = "随包许可证与第三方声明", Bounds = new Rectangle(8, 237, 430, 24) };
            notices.LinkClicked += delegate { Process.Start(new ProcessStartInfo(Path.Combine(packageRoot, "THIRD_PARTY_NOTICES.md")) { UseShellExecute = true }); };
            disclosure.Controls.Add(notices);
            bool release = policy["channel"] == "public";
            LabelAt(disclosure, release ? "" : "开发测试版 · 正式法务文本待补齐，不可公开发布", 8, 265, 445, 24, 9, true).ForeColor = red;
            accepted = new CheckBox { Text = release ? "我已阅读上述说明和协议，同意开始安装" : "我已阅读上述说明，仅用于开发测试", Bounds = new Rectangle(8, 298, 445, 32) };
            disclosure.Controls.Add(accepted);
            primary.Enabled = false;
            accepted.CheckedChanged += delegate { primary.Enabled = accepted.Checked; };
        }
        void AddDisclosureLink(Dictionary<string, string> policy, string key, string title, int x, int y) {
            string value = policy[key];
            var link = new LinkLabel { Text = title + (String.IsNullOrEmpty(value) ? "（待配置）" : ""), Bounds = new Rectangle(x, y, key.StartsWith("host") ? 110 : 220, 28), Enabled = !String.IsNullOrEmpty(value) };
            link.LinkClicked += delegate {
                Uri uri;
                if (Uri.TryCreate(value, UriKind.Absolute, out uri) && uri.Scheme == "https" && String.IsNullOrEmpty(uri.UserInfo)) Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
            };
            disclosure.Controls.Add(link);
        }

        int ScaleY(int pixels) { return (int)Math.Round(pixels * Font.Height / 17.0); }
        Label LabelAt(Control parent, string text, int x, int y, int width, int height, float size, bool bold) {
            Label label = new Label { Text = text, Bounds = new Rectangle(x, y, width, height), Font = new Font("Microsoft YaHei UI", size, bold ? FontStyle.Bold : FontStyle.Regular), ForeColor = ink, AutoEllipsis = true };
            parent.Controls.Add(label); return label;
        }
        Button ButtonAt(string text, int x, int y, int width, bool accent) {
            Button button = new Button { Text = text, Bounds = new Rectangle(x, y, width, 38), FlatStyle = FlatStyle.Flat, BackColor = accent ? red : Color.White, ForeColor = accent ? Color.White : ink, Cursor = Cursors.Hand, UseVisualStyleBackColor = false };
            button.FlatAppearance.BorderColor = accent ? red : Color.FromArgb(219, 222, 226);
            Controls.Add(button); return button;
        }
        void StartInstall() {
            if (accepted == null || !accepted.Checked) return;
            disclosure.Visible = false;
            try {
                if (worker != null) { worker.Dispose(); worker = null; }
                File.Delete(statePath); File.Delete(statePath + ".cancel");
                log.Clear(); lastState = ""; phase = ""; executable = ""; cancelRequested = false; succeeded = false;
                logWriter = new StreamWriter(Path.Combine(runRoot, "installation.log"), true, new UTF8Encoding(false));
                logWriter.AutoFlush = true;
                logWriter.WriteLine("\r\n=== " + DateTime.Now.ToString("s") + " ===");
                // Paths are carried in the environment, never interpolated into code.
                string command = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$OutputEncoding=[Console]::OutputEncoding;try { & $env:CANNBOT_UI_INSTALLER -DisclosureAccepted -PackageRoot $env:CANNBOT_UI_PACKAGE -ProgressPath $env:CANNBOT_UI_PROGRESS;exit 0 } catch { [Console]::Error.WriteLine($_.Exception.Message);exit 1 }";
                string workerScript = Path.Combine(runRoot, "installation-worker.ps1");
                File.WriteAllText(workerScript, command, new UTF8Encoding(false));
                ProcessStartInfo info = new ProcessStartInfo("powershell.exe", "-NoProfile -NonInteractive -OutputFormat Text -ExecutionPolicy Bypass -File \"" + workerScript + "\"");
                info.UseShellExecute = false; info.CreateNoWindow = true;
                info.RedirectStandardOutput = true; info.RedirectStandardError = true;
                info.StandardOutputEncoding = Encoding.UTF8; info.StandardErrorEncoding = Encoding.UTF8;
                info.EnvironmentVariables["CANNBOT_UI_INSTALLER"] = installer;
                info.EnvironmentVariables["CANNBOT_UI_PACKAGE"] = packageRoot;
                info.EnvironmentVariables["CANNBOT_UI_PROGRESS"] = statePath;
                worker = new Process { StartInfo = info };
                worker.OutputDataReceived += delegate(object sender, DataReceivedEventArgs args) { if (args.Data != null) lines.Enqueue(args.Data); };
                worker.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs args) { if (args.Data != null) lines.Enqueue(args.Data); };
                worker.Start(); worker.BeginOutputReadLine(); worker.BeginErrorReadLine();
                busy = true; Result = 1; watch.Restart(); secondary.Enabled = false;
                RenderPhase("detect", null); timer.Start();
            } catch (Exception error) { Finish(false, "无法开始安装：" + error.Message); }
        }
        void CancelDownload() {
            if (cancelRequested) return;
            try {
                File.WriteAllText(statePath + ".cancel", "cancel"); cancelRequested = true;
                description.Text = "正在取消下载并清理临时文件，请稍候…"; primary.Enabled = false;
            } catch (Exception error) { MessageBox.Show(this, error.Message, "无法取消"); }
        }
        void DrainLog() {
            string line;
            while (lines.TryDequeue(out line)) {
                if (logWriter != null) logWriter.WriteLine(line);
                if (log.TextLength > 120000) log.Text = log.Text.Substring(log.TextLength - 60000);
                log.AppendText(line + Environment.NewLine);
            }
        }
        void RefreshInstall() {
            progress.Advance();
            DrainLog();
            try {
                string state = File.ReadAllText(statePath, Encoding.UTF8);
                if (state != lastState) {
                    var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(state);
                    RenderPhase((string)data["phase"], data); lastState = state;
                }
            } catch (IOException) { } catch (ArgumentException) { }
            elapsed.Text = "已用时 " + watch.Elapsed.ToString(@"mm\:ss") + "  ·  安装日志已自动保存";
            if (worker == null || !worker.HasExited) return;
            worker.WaitForExit(); DrainLog();
            bool ok = worker.ExitCode == 0 && phase == "complete" && File.Exists(executable);
            Finish(ok, cancelRequested && phase == "download" ? "下载已取消，点击重试可重新开始。" : "请展开日志查看具体原因，处理后点击重试。");
        }
        void RenderPhase(string next, Dictionary<string, object> data) {
            phase = next;
            int current = next == "detect" ? 0 : next == "download" ? 1 : next == "install" ? 2 : next == "profile" ? 3 : next == "plugin" ? 4 : 5;
            for (int i = 0; i < steps.Length; i++) {
                string label = new string[] { "检查环境", "下载宿主程序", "安装宿主程序", "准备运行环境", "安装 CANNBot" }[i];
                steps[i].Text = (i < current ? "✓ " : (i + 1).ToString("00")) + "   " + label;
                steps[i].ForeColor = i == current ? red : i < current ? ink : muted;
            }
            stage.Text = current < 5 ? "步骤 " + (current + 1) + " / 5" : "安装完成";
            heading.Text = next == "download" ? "正在下载宿主程序" : next == "install" ? "正在安装宿主程序" : next == "plugin" ? "正在安装 CANNBot" : current == 3 ? "正在准备运行环境" : "正在检查环境";
            description.Text = next == "download" ? "正在获取工作台所需的宿主安装包。\n下载完成后将自动继续安装。" : next == "profile" ? "正在后台初始化工作台配置。\n无需打开或登录宿主程序。" : next == "install" ? "正在安装宿主程序。\n请保持此窗口打开，安装完成后会自动继续。" : next == "plugin" ? "正在准备昇腾开发工作台与远程连接功能。\n首次安装可能需要一些时间。" : "正在检查已有安装并准备所需环境。\n已有的宿主和用户数据会自动复用。";
            primary.Text = next == "download" ? "取消下载" : "正在安装…";
            primary.Enabled = next == "download" && !cancelRequested;
            progress.Style = ProgressBarStyle.Marquee;
            metric.Text = "正在处理，请稍候…";
            if (next == "download" && data != null) {
                double received = Convert.ToDouble(data["received"]), total = Convert.ToDouble(data["total"]), speed = Convert.ToDouble(data["speed"]);
                if (total > 0) { progress.Style = ProgressBarStyle.Continuous; progress.Value = Math.Max(0, Math.Min(100, (int)(received * 100 / total))); }
                metric.Text = (total > 0 ? progress.Value + "%    " : "") + (received / 1048576).ToString("0.0") + (total > 0 ? " / " + (total / 1048576).ToString("0.0") : "") + " MB    ·    " + (speed / 1048576).ToString("0.0") + " MB/s";
            }
            progress.AccessibleName = metric.Text;
            if (next == "complete" && data != null) executable = Convert.ToString(data["executable"]);
            if (cancelRequested && next == "download") description.Text = "正在取消下载并清理临时文件，请稍候…";
        }
        void Finish(bool ok, string message) {
            timer.Stop(); watch.Stop(); busy = false; succeeded = ok; Result = ok ? 0 : 1;
            if (logWriter != null) { logWriter.Dispose(); logWriter = null; }
            progress.Style = ProgressBarStyle.Continuous; progress.Value = ok ? 100 : 0;
            progress.Invalidate();
            stage.Text = ok ? "安装完成" : cancelRequested ? "已取消" : "安装未完成";
            heading.Text = ok ? "一切就绪，开始使用" : cancelRequested ? "下载已取消" : "安装遇到了一点问题";
            description.Text = ok ? "CANNBot 昇腾开发工作台已安装。\n打开工作台，在侧栏选择 CANNBot 即可开始。" : message;
            metric.Text = ok ? "✓  已完成全部安装步骤" : "安装日志已保存，可展开查看详情";
            progress.AccessibleName = metric.Text;
            secondary.Enabled = true; primary.Enabled = true;
            primary.Text = ok ? "打开工作台" : "重试安装";
        }
        protected override void Dispose(bool disposing) {
            if (disposing) { timer.Dispose(); if (worker != null) worker.Dispose(); if (logWriter != null) logWriter.Dispose(); }
            base.Dispose(disposing);
        }
        public static int Run(string installer, string package, string folder) {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var window = new SetupWindow(installer, package, folder)) { Application.Run(window); return window.Result; }
        }
        [STAThread]
        public static void Main() {
            try {
                Environment.Exit(Run(Environment.GetEnvironmentVariable("CANNBOT_GUI_INSTALLER"), Environment.GetEnvironmentVariable("CANNBOT_GUI_PACKAGE"), Environment.GetEnvironmentVariable("CANNBOT_GUI_RUNROOT")));
            } catch (Exception error) {
                MessageBox.Show(error.Message, "CANNBot Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Environment.Exit(1);
            }
        }
    }
}
