// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under CANN Open Software License Agreement Version 2.0. See LICENSE.
using System;
using System.Net;
using System.Text;
using System.IO;

public static class CANNBotAskpass {
    static string Json(string value) {
        var result = new StringBuilder("\"");
        foreach (char c in value) {
            if (c == '\\' || c == '"') result.Append('\\').Append(c);
            else if (c < 32) result.Append("\\u").Append(((int)c).ToString("x4"));
            else result.Append(c);
        }
        return result.Append('"').ToString();
    }
    public static int Main(string[] args) {
        try {
            if (args.Length != 1 || !String.IsNullOrEmpty(Environment.GetEnvironmentVariable("SSH_ASKPASS_PROMPT"))) return 1;
            int port = int.Parse(Environment.GetEnvironmentVariable("CANNBOT_ASKPASS_PORT"));
            if (port < 1 || port > 65535) return 1;
            var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/");
            request.Proxy = null;
            request.Method = "POST";
            request.Timeout = 125000;
            request.Headers["Authorization"] = "Bearer " + Environment.GetEnvironmentVariable("CANNBOT_ASKPASS_TOKEN");
            request.ContentType = "application/json";
            byte[] body = Encoding.UTF8.GetBytes("{\"prompt\":" + Json(args[0]) + ",\"callId\":" + Json(Environment.GetEnvironmentVariable("CANNBOT_ASKPASS_CALL") ?? "") + "}");
            request.ContentLength = body.Length;
            using (var stream = request.GetRequestStream()) stream.Write(body, 0, body.Length);
            using (var response = request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8)) {
                byte[] answer = Encoding.UTF8.GetBytes(reader.ReadToEnd() + "\n");
                using (var stdout = Console.OpenStandardOutput()) stdout.Write(answer, 0, answer.Length);
                Array.Clear(answer, 0, answer.Length);
            }
            return 0;
        } catch { return 1; }
    }
}
