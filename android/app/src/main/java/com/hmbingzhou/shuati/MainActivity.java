package com.hmbingzhou.shuati;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/**
 * 安卓外壳：启动内置 Python 服务（webui_server），再用 WebView 打开 http://127.0.0.1:<port>。
 *
 * - Python 侧入口为 app/src/main/python/entry.py 的 start(home) → 返回端口号；
 * - home 为应用私有目录（getFilesDir），对应 Python 的 SHUATI_HOME；
 * - 返回键先交给网页（window.__shuatiAndroidBack），未被处理才退出应用；
 * - 实现 onShowFileChooser，使编辑器里的“上传新图片 / 拍照”可用。
 */
public class MainActivity extends Activity {

    private static final int REQ_FILE_CHOOSER = 1001;

    private WebView webView;
    private ValueCallback<Uri[]> pendingFileCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.setBackgroundColor(Color.parseColor("#F2F5FB"));
        setContentView(root);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);          // 设置项存在 localStorage
        settings.setTextZoom(100);                    // 不让系统字体缩放打乱布局
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE); // 服务器已发 no-cache，避免旧前端残留

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String host = uri.getHost();
                if (host != null && (host.equals("127.0.0.1") || host.equals("localhost"))) {
                    return false;   // 站内（本地服务）导航
                }
                // 外部链接（例如 GitHub 仓库地址）交给系统浏览器
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (Exception ignored) {
                }
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (pendingFileCallback != null) {
                    pendingFileCallback.onReceiveValue(null);
                }
                pendingFileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), REQ_FILE_CHOOSER);
                    return true;
                } catch (Exception e) {
                    pendingFileCallback = null;
                    return false;
                }
            }
        });

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        final String home = getFilesDir().getAbsolutePath();
        new Thread(() -> {
            try {
                PyObject entry = Python.getInstance().getModule("entry");
                final int port = entry.callAttr("start", home).toJava(int.class);
                runOnUiThread(() -> webView.loadUrl("http://127.0.0.1:" + port + "/"));
            } catch (final Exception e) {
                final String msg = String.valueOf(e.getMessage());
                runOnUiThread(() -> webView.loadDataWithBaseURL(null,
                        "<html><body style='font-family:sans-serif;padding:24px'>"
                                + "<h3>本地服务启动失败</h3><pre style='white-space:pre-wrap'>"
                                + msg + "</pre></body></html>",
                        "text/html", "utf-8", null));
            }
        }, "shuati-python-server").start();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER) {
            if (pendingFileCallback != null) {
                pendingFileCallback.onReceiveValue(
                        WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                pendingFileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        if (webView == null) {
            finish();
            return;
        }
        // 先让网页处理（关弹窗 / 回首页），返回 1 表示已消费
        webView.evaluateJavascript(
                "(window.__shuatiAndroidBack && window.__shuatiAndroidBack()) ? 1 : 0",
                value -> {
                    if (!"1".equals(value)) {
                        finish();
                    }
                });
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
