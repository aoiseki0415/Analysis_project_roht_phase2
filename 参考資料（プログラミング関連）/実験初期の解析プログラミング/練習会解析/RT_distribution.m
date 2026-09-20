
% 解析したいブロックに応じてこちらで変更する
block_num = 2;

folderPath = "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験リハ解析/rht-mvp01/data/test-001/20260805/behave";
resultPath = '/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/ドキュメント/MATLAB/sandboxロート案件2/練習会解析/結果/RT関連';


% フォルダ内のCSV一覧を取得
files = dir(fullfile(folderPath, "*.csv"));

% 1つ目のCSVを読み込む
T = readtable(fullfile(files(1).folder, files(block_num).name));



%% 

% behaviorだけの解析の時は、sysではない方のデータを用いる

RT_data = T.RT_ms_;
RT_data = RT_data(~isnan(RT_data));


%% 

% プロット
figure1 = figure('Position', [1 1 800 500]);


plot(RT_data, ...
    'LineStyle', '-', ...
    'Color', [0.3, 0.3, 0.3], ...
    'LineWidth', 2);

hold on

xticks([0 80 160 240 320]);
xlim([0 320]);

set(gca, 'FontSize', 20);
ax = gca;
ax.TickDir = 'out';
ax.FontName = 'arial';
set(ax, 'box', 'off');

xlabel('trial', 'FontSize', 28);
ylabel({'Reaction Time (ms)'}, 'FontSize', 28);
yticks(0:500:5000);

if max(RT_data) > 0
    ylim([0 max(RT_data)*1.2]);
end

block_num = num2str(block_num);
pngPath = fullfile(resultPath, ['Block' block_num '_RT_trend.png']);
saveas(gcf, pngPath);

% close all


%% 

% パラメータ設定
lwin = 30;
timewidth = 1:1:2000;


wavenow = KernelDensity(RT_data, lwin, timewidth, 0);

% それを利用して、スムージングを行う
% データを見やすくした
wavenow = smoothdata(wavenow, 'movmean', 50);

% 念のため縦ベクトルにそろえる
y = wavenow(:);

% x軸はRTの時間幅にそろえる
x = timewidth(:)';


% 塗りつぶし用のデータ作成
x_fill = [x, fliplr(x)];
y_fill = [y', zeros(1, numel(y))];


%% 

miss = T.ResponseType;
miss_count = sum(miss == "mistouch");


%% 


% プロット
figure1 = figure('Position', [1 1 800 500]);
fill(x_fill, y_fill, [0.3, 0.3, 0.3], ...
    'FaceAlpha', 0.3, ...
    'EdgeColor', [0.3, 0.3, 0.3], ...
    'LineWidth', 3);

hold on
xticks([0 500 1000 1500 2000]);
xlim([0 2000]);

set(gca, 'FontSize', 20);
ax = gca;
ax.YAxis.Exponent = -3;
ax.LineWidth = 2;
ax.TickDir = 'out';
ax.FontName = 'arial';
set(ax, 'box', 'off');

xlabel('Reaction Time (ms)', 'FontSize', 28);
ylabel({'Density'}, 'FontSize', 28);
yticks(0:0.005:0.1);

if max(y) > 0
    ylim([0 max(y)*1.2]);
end


text(0.9, 0.9, sprintf('Mistouch: %d', miss_count), ...
    'Units', 'normalized', ...
    'HorizontalAlignment', 'right', ...
    'VerticalAlignment', 'top', ...
    'FontSize', 18, ...
    'FontName', 'Arial');


block_num = num2str(block_num);
pngPath = fullfile(resultPath, ['Block' block_num '_RT_distribution.png']);
saveas(gcf, pngPath);

% close all

