% EEGLABを起動
addpath(genpath('/Users/aoiseki/OneDrive/ドキュメント/MATLAB/eeglab2024.2'), '-end');
% addpath(genpath('C:\Users\あおい\OneDrive\ドキュメント\MATLAB\eeglab2024.2'), '-end');


folderPath = "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験リハ解析/rht-mvp01/data/test-001/20260805/behave";
folderPath2 = '/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験リハ解析/rht-mvp01/EEG Data';

resultPath = '/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/ドキュメント/MATLAB/sandboxロート案件2/練習会解析/結果/';
resultPath_ERP = fullfile(resultPath, 'EEG関連', 'ERP');
resultPath_Stimulus = fullfile(resultPath_ERP, 'Stimulus_related');
resultPath_Keypress = fullfile(resultPath_ERP, 'keypress_related');
resultPath_Power = fullfile(resultPath, 'EEG関連', 'Power');
resultPath_PowerStimulus = fullfile(resultPath_Power, 'stimulus_related');
resultPath_PowerKeypress = fullfile(resultPath_Power, 'keypress_related');

resultFolders = {resultPath_ERP, resultPath_Stimulus, resultPath_Keypress, ...
    resultPath_Power, resultPath_PowerStimulus, resultPath_PowerKeypress};
for folderIndex = 1:numel(resultFolders)
    if ~exist(resultFolders{folderIndex}, 'dir')
        mkdir(resultFolders{folderIndex});
    end
end

% ブロックごとの行動データを読み込む
block1_file = dir(fullfile(folderPath, "*block1_results.csv"));
block2_file = dir(fullfile(folderPath, "*block2_results.csv"));

if numel(block1_file) ~= 1 || numel(block2_file) ~= 1
    error('block1_results.csv または block2_results.csv を一意に特定できません。');
end

behav_block1 = readtable(fullfile(block1_file.folder, block1_file.name));
behav_block2 = readtable(fullfile(block2_file.folder, block2_file.name));

% EEGデータとイベントログを読み込む
eeg_file = dir(fullfile(folderPath2, "*test-001*.md.csv"));
event_file = dir(fullfile(folderPath, "*_events.csv"));

if numel(eeg_file) ~= 1 || numel(event_file) ~= 1
    error('EEGファイルまたはevents.csvを一意に特定できません。');
end

EEG = readtable(fullfile(eeg_file.folder, eeg_file.name));
event_log = readtable(fullfile(event_file.folder, event_file.name));

% EEGファイル名（例: test-001_FLEX2_...）から参加者IDを取得する。
subID_tokens = regexp(eeg_file.name, '^(test-\d+)_', 'tokens', 'once');
if isempty(subID_tokens)
    error('EEGファイル名から参加者IDを取得できません。');
end
subID = strrep(subID_tokens{1}, '-', '');  % 例: test-001 -> test001

% EEGテーブルを数値行列へ変換する。
EEG_matrix = table2array(EEG);
% Cortexがリアルタイムで算出したOriginalTimestampをmsへ変換する。
EEG_time_ms = EEG.OriginalTimestamp * 1000;

% EEGのサンプリング周波数と、イベント前後のepoch範囲
Fs = 256;
epoch_window_seconds = 0.5;
epoch_padding_ms = epoch_window_seconds * 1000;

% 頭皮EEGの全32チャンネルだけを選択する。
eeg_channel_labels = {'Cz', 'Fz', 'Fp1', 'F7', 'F3', 'FC1', 'C3', 'FC5', ...
    'FT9', 'T7', 'CP5', 'CP1', 'P3', 'P7', 'PO9', 'O1', 'Pz', 'Oz', ...
    'O2', 'PO10', 'P8', 'P4', 'CP2', 'CP6', 'T8', 'FT10', 'FC6', ...
    'C4', 'FC2', 'F4', 'F8', 'Fp2'};
eeg_channel_names = cellfun(@(x) matlab.lang.makeValidName(['EEG.' x]), ...
    eeg_channel_labels, 'UniformOutput', false);
eeg_variable_names = cellfun(@(x) matlab.lang.makeValidName(x), ...
    EEG.Properties.VariableNames, 'UniformOutput', false);
[channels_found, eeg_channel_indices] = ismember(eeg_channel_names, eeg_variable_names);

if ~all(channels_found)
    error('EEGチャンネルが見つかりません: %s', ...
        strjoin(eeg_channel_names(~channels_found), ', '));
end

EEG_signal = EEG_matrix(:, eeg_channel_indices);


%% 連続EEGのフィルタリング

% epochingより前の連続データに対して、全32チャンネルを同時に処理する。
% ハムカットフィルタ
% ポルトガル由来と考えられるため、交流は50Hzとして扱う
% 外部関数は使わず、49--51 Hzのバンドストップフィルタで除去する。
EEG_filtered = bandstop(EEG_signal, [49 51], Fs);

% バンドパスフィルター
% 1-100Hzに
EEG_filtered = bandpass(EEG_filtered, [1 100], Fs);

% EEGのトレンド除去（detrend関数を用いる）
EEG_filtered = detrend(EEG_filtered);

%% ブロックごとの刺激提示・キー押し時刻（UnixTime, ms）

% PCのOS時刻を使用するため、TiltOnsetSys(ms) と KeyPressSys(ms) を用いる。
stimulus_onset_block1 = behav_block1.TiltOnsetSys_ms_;
keypress_onset_block1 = behav_block1.KeyPressSys_ms_;

stimulus_onset_block2 = behav_block2.TiltOnsetSys_ms_;
keypress_onset_block2 = behav_block2.KeyPressSys_ms_;

% 1列目: stimulus onset、2列目: keypress の時刻（ms）
% 刺激提示またはキー押しが欠損した行（ミスタッチ等）を除外する。
event_time_block1 = [stimulus_onset_block1, keypress_onset_block1];
event_time_block1 = event_time_block1(~any(isnan(event_time_block1), 2), :);

event_time_block2 = [stimulus_onset_block2, keypress_onset_block2];
event_time_block2 = event_time_block2(~any(isnan(event_time_block2), 2), :);

% 各ブロックは320 trialであることを確認する。
if size(event_time_block1, 1) ~= 320 || size(event_time_block2, 1) ~= 320
    error('NaN除去後のtrial数が320ではありません。Block 1: %d行、Block 2: %d行', ...
        size(event_time_block1, 1), size(event_time_block2, 1));
end

% 後続の解析で使いやすいよう、NaN除去後の各時刻ベクトルも更新する。
stimulus_onset_block1 = event_time_block1(:, 1);
keypress_onset_block1 = event_time_block1(:, 2);
stimulus_onset_block2 = event_time_block2(:, 1);
keypress_onset_block2 = event_time_block2(:, 2);


%% events.csvのblock開始・終了時刻で連続EEGをブロックごとに分割

% PCのOS時刻であるSysUnixTime(ms) を使用する。
event_type = string(event_log.Event);
event_detail = string(event_log.Detail);
event_time_ms = event_log.SysUnixTime_ms_;

block1_start_ms = event_time_ms(event_type == "block_start" & event_detail == "1");
block1_end_ms   = event_time_ms(event_type == "block_end"   & event_detail == "1");
block2_start_ms = event_time_ms(event_type == "block_start" & event_detail == "2");
block2_end_ms   = event_time_ms(event_type == "block_end"   & event_detail == "2");

if numel(block1_start_ms) ~= 1 || numel(block1_end_ms) ~= 1 || ...
        numel(block2_start_ms) ~= 1 || numel(block2_end_ms) ~= 1
    error('events.csvからblock 1/2の開始・終了時刻を一意に取得できません。');
end

% 最初・最後のイベントの前後500 msをepoch化できるように余白を含める。
is_block1 = EEG_time_ms >= block1_start_ms - epoch_padding_ms & ...
    EEG_time_ms <= block1_end_ms + epoch_padding_ms;
is_block2 = EEG_time_ms >= block2_start_ms - epoch_padding_ms & ...
    EEG_time_ms <= block2_end_ms + epoch_padding_ms;

EEG_block1 = EEG_matrix(is_block1, :);
EEG_block2 = EEG_matrix(is_block2, :);

% epochingには、フィルタ済みの32チャンネルEEGを用いる。
EEG_signal_block1 = EEG_filtered(is_block1, :);
EEG_signal_block2 = EEG_filtered(is_block2, :);

EEG_time_ms_block1 = EEG_time_ms(is_block1);
EEG_time_ms_block2 = EEG_time_ms(is_block2);

fprintf('Block 1 EEG: %d samples\n', size(EEG_block1, 1));
fprintf('Block 2 EEG: %d samples\n', size(EEG_block2, 1));


%% Epoching: stimulus onset / keypress の前後500 ms
% epoching_generalはサンプル番号をcueとして受け取るため、
% Unix時刻（ms）を各ブロック内の最も近いEEGサンプル番号へ変換する。

% epoching_general内では開始点に +1 が入るため、
% [-129 128] を渡すと cue-128 : cue+128、すなわち -500 : +500 ms の257点になる。
epoch_half_window_samples = round(epoch_window_seconds * Fs);
tim = [-epoch_half_window_samples - 1, epoch_half_window_samples];
zyn = 0;

stimulus_cues_block1 = interp1(EEG_time_ms_block1, ...
    (1:numel(EEG_time_ms_block1))', stimulus_onset_block1, 'nearest');
keypress_cues_block1 = interp1(EEG_time_ms_block1, ...
    (1:numel(EEG_time_ms_block1))', keypress_onset_block1, 'nearest');
stimulus_cues_block2 = interp1(EEG_time_ms_block2, ...
    (1:numel(EEG_time_ms_block2))', stimulus_onset_block2, 'nearest');
keypress_cues_block2 = interp1(EEG_time_ms_block2, ...
    (1:numel(EEG_time_ms_block2))', keypress_onset_block2, 'nearest');

% 前後500 msを切り出せるか確認する。
all_cues = {stimulus_cues_block1, keypress_cues_block1, ...
    stimulus_cues_block2, keypress_cues_block2};
all_lengths = [size(EEG_signal_block1, 1), size(EEG_signal_block1, 1), ...
    size(EEG_signal_block2, 1), size(EEG_signal_block2, 1)];
for i = 1:numel(all_cues)
    if any(all_cues{i} < -tim(1)) || any(all_cues{i} + tim(2) > all_lengths(i))
        error('イベント前後500 ms分のEEGが不足しているtrialがあります。');
    end
end

% 各行列の次元: 時間サンプル (257) × trial (320) × EEGチャンネル (32)
n_channels = numel(eeg_channel_indices);
n_epoch_samples = tim(2) - tim(1);
epoch_stimulus_block1 = zeros(n_epoch_samples, numel(stimulus_cues_block1), n_channels);
epoch_keypress_block1 = zeros(n_epoch_samples, numel(keypress_cues_block1), n_channels);
epoch_stimulus_block2 = zeros(n_epoch_samples, numel(stimulus_cues_block2), n_channels);
epoch_keypress_block2 = zeros(n_epoch_samples, numel(keypress_cues_block2), n_channels);

for ch = 1:n_channels
    epoch_stimulus_block1(:, :, ch) = epoching_general( ...
        EEG_signal_block1(:, ch), stimulus_cues_block1, tim, zyn);
    epoch_keypress_block1(:, :, ch) = epoching_general( ...
        EEG_signal_block1(:, ch), keypress_cues_block1, tim, zyn);
    epoch_stimulus_block2(:, :, ch) = epoching_general( ...
        EEG_signal_block2(:, ch), stimulus_cues_block2, tim, zyn);
    epoch_keypress_block2(:, :, ch) = epoching_general( ...
        EEG_signal_block2(:, ch), keypress_cues_block2, tim, zyn);
end


%% ERPプロット: block 1/2 × stimulus/keypress × 全32チャンネル
% epoching_generalの切り出し範囲（cue + tim(1) + 1 : cue + tim(2)）に
% 対応する時刻ベクトルを、256 Hzからms単位で作成する。

time_ms = (tim(1) + 1 : tim(2)) / Fs * 1000;

epoch_conditions = {epoch_stimulus_block1, epoch_keypress_block1, ...
    epoch_stimulus_block2, epoch_keypress_block2};
condition_blocks = [1, 1, 2, 2];
condition_events = {'stimulus', 'keypress', 'stimulus', 'keypress'};
condition_folders = {resultPath_Stimulus, resultPath_Keypress, ...
    resultPath_Stimulus, resultPath_Keypress};

for conditionIndex = 1:numel(epoch_conditions)
    epoched_data_condition = epoch_conditions{conditionIndex};
    blockNumber = condition_blocks(conditionIndex);
    eventName = condition_events{conditionIndex};
    saveFolder = condition_folders{conditionIndex};


    for ch = 1:n_channels % n_channels
        channelName = eeg_channel_labels{ch};
        epoched_data_channel = epoched_data_condition(:, :, ch);
        ERP = mean(epoched_data_channel, 2, 'omitnan');

        figure1 = figure('Position', [1 1 800 500]);
        hold on

        % 各trialを薄い灰色、trial平均ERPを橙色で描画する。
        for trialIndex = 1:size(epoched_data_channel, 2)
            t1 = plot(time_ms, epoched_data_channel(:, trialIndex), '-', ...
                'LineWidth', 1.5, 'Color', [0.2, 0.2, 0.2]);
            t1.Color(4) = 0.06;
        end

        t2 = plot(time_ms, ERP, '-', ...
            'LineWidth', 3.5, 'Color', [0.8, 0.33, 0.15]);
        t2.Color(4) = 1;

        xlim([min(time_ms), max(time_ms)]);
        xticks(-500:100:500);
        ylim([-50 50]);
        yticks(-100:25:100);

        set(gca, 'FontSize', 16);
        ylabel('Amplitude (\muV)', 'FontName', 'Arial', 'FontSize', 28);
        xlabel('Time (ms)', 'FontName', 'Arial', 'FontSize', 30);
        title(sprintf('Block %d - %s - %s', blockNumber, eventName, channelName), ...
            'FontName', 'Arial', 'FontSize', 24);
        xline(0, '--', 'Color', [0.5, 0.5, 0.5], 'LineWidth', 3);
        yline(0, '-', 'LineWidth', 1, 'Color', [0.2, 0.2, 0.2]);
        ax = gca;
        ax.LineWidth = 2;
        ax.TickDir = 'out';
        ax.FontName = 'Arial';
        set(ax, 'Box', 'off');

        % ファイル名: 参加者ID、block番号、イベント種別、チャンネル名
        saveName = sprintf('%s_Block%d_%s_%s.png', ...
            subID, blockNumber, eventName, channelName);
        saveas(figure1, fullfile(saveFolder, saveName));
        pause(3);
        close(figure1);
    end
end



%% パワー変化量: block 1/2 × stimulus/keypress × 指定6チャンネル

% power_nextはFs=256 Hzに合わせた200 ms窓を、1サンプルずつ移動して計算する。

power_channel_labels = {'Fz', 'Cz', 'Pz', 'Oz', 'C3', 'C4'};
[power_channels_found, power_channel_indices] = ismember( ...
    power_channel_labels, eeg_channel_labels);

if ~all(power_channels_found)
    error('パワー解析用チャンネルが見つかりません: %s', ...
        strjoin(power_channel_labels(~power_channels_found), ', '));
end

power_condition_names = {'Block1_stimulus', 'Block1_keypress', ...
    'Block2_stimulus', 'Block2_keypress'};
power_condition_folders = {resultPath_PowerStimulus, resultPath_PowerKeypress, ...
    resultPath_PowerStimulus, resultPath_PowerKeypress};
baseline_window_ms = [-500, -300];

% 次元: 周波数 (1--50 Hz) × 時間窓 × チャンネル × 条件
power_change_percent = [];

for conditionIndex = 1:numel(epoch_conditions)
    epoched_data_condition = epoch_conditions{conditionIndex};

    for powerChannelIndex = 1:numel(power_channel_indices)
        epoch_channel_data = epoched_data_condition(:, :, ...
            power_channel_indices(powerChannelIndex));

        [power_all_trials, power_frequency_hz, power_time_ms] = ...
            power_next(epoch_channel_data, Fs, time_ms);

        baseline_indices = power_time_ms >= baseline_window_ms(1) & ...
            power_time_ms <= baseline_window_ms(2);
        if ~any(baseline_indices)
            error('指定したbaseline区間に対応するパワー時間窓がありません。');
        end

        % trial平均後の時間周波数パワーからbaselineを抽出し、％変化へ変換する。
        power_mean_trials = mean(power_all_trials, 3, 'omitnan');
        baseline_power = mean(power_mean_trials(:, baseline_indices), 2, 'omitnan');
        power_change_percent(:, :, powerChannelIndex, conditionIndex) = ...
            bsxfun(@rdivide, power_mean_trials, baseline_power) * 100 - 100;

        %% パワー変化マップのプロットと保存
        
        power_change_map = power_change_percent(:, :, powerChannelIndex, conditionIndex);
        blockNumber = condition_blocks(conditionIndex);
        eventName = condition_events{conditionIndex};
        channelName = power_channel_labels{powerChannelIndex};

        clims3 = [-50 50];
        figure2 = figure('Position',[1 1 800 500]);
        imagesc(power_time_ms, power_frequency_hz, power_change_map, clims3);
        colormap('jet');
        hColorbar = colorbar;
        set(hColorbar, 'FontSize', 20, 'Ticks', -100:25:100,'FontName', 'Arial');
        hColorbar.Label.String = 'Power change, %';
        hColorbar.Label.Rotation = 270;
        set(gca, 'YDir', 'normal', 'FontSize', 17, ...
            'YTick', [1 10 20 30 40 50], ...
            'XTick', -400:100:400, 'YLim', [1 50], 'XLim', [-400 400],'FontName', 'Arial');
        ylabel('Frequency (Hz)', 'FontName', 'Arial', 'FontSize', 28);
        xlabel('Time (ms)', 'FontName', 'Arial', 'FontSize', 30);
        title(sprintf('Block %d - %s - %s', blockNumber, eventName, channelName), ...
            'FontName', 'Arial', 'FontSize', 22);
        xline(0, '--', 'Color', 'w', 'LineWidth', 2);

        saveName = sprintf('%s_Block%d_%s_%s_power.png', ...
            subID, blockNumber, eventName, channelName);
        saveas(figure2, fullfile(power_condition_folders{conditionIndex}, saveName));
        pause(2);
        close(figure2);

    end

    fprintf('Power calculation complete: %s\n', ...
        power_condition_names{conditionIndex});
end

