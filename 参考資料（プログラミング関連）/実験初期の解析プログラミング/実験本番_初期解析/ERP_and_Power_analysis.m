% EEGLABを起動
addpath(genpath('/Users/aoiseki/OneDrive/ドキュメント/MATLAB/eeglab2024.2'), '-end');

% 解析する被験者番号を指定する。追加・削除はこのリストだけを編集する。
% participant_ids = {'101', '104', '106'};
participant_ids = {'106'};
block_numbers = 1:6;

% 本番データの親フォルダ
dataRoot = "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_初期解析";

% 出力先の親フォルダ。被験者ごとにIDフォルダを作成する。
resultRoot = '/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/ドキュメント/MATLAB/sandboxロート案件2/実験本番_初期解析/結果/EEG関連';

% EEGのサンプリング周波数と、イベント前後のepoch範囲
Fs = 256;
epoch_window_seconds = 0.5;
% 最近傍EEGサンプルへの丸めで端のepochが1点不足しないよう、
% 前後500 msに加えて2サンプル分の安全マージンを確保する。
epoch_padding_ms = epoch_window_seconds * 1000 + 2 / Fs * 1000;
epoch_half_window_samples = round(epoch_window_seconds * Fs);
tim = [-epoch_half_window_samples - 1, epoch_half_window_samples];
zyn = 0;
time_ms = (tim(1) + 1 : tim(2)) / Fs * 1000;

% ERP・パワー解析で共通して用いるチャンネル。
% この9chだけを読み出し、前処理・エポック化・図作成を行う。
analysis_channel_labels = {'Fz', 'Cz', 'Pz', 'C3', 'C4', ...
    'Fp1', 'Fp2', 'O1', 'O2'};

% パワー解析用設定（ERPと同じチャンネルを用いる）
power_channel_labels = analysis_channel_labels;
baseline_window_ms = [-500, -300];

for participant_index = 1:numel(participant_ids)
    participant_id = participant_ids{participant_index};
    subID = ['ID' participant_id];

    % 被験者ごとの結果フォルダを作成する。
    resultPath = fullfile(resultRoot, subID);
    resultPath_ERP = fullfile(resultPath, 'ERP');
    resultPath_Stimulus = fullfile(resultPath_ERP, 'Stimulus_related');
    resultPath_Keypress = fullfile(resultPath_ERP, 'keypress_related');
    resultPath_Power = fullfile(resultPath, 'Power');
    resultPath_PowerStimulus = fullfile(resultPath_Power, 'stimulus_related');
    resultPath_PowerKeypress = fullfile(resultPath_Power, 'keypress_related');
    resultFolders = {resultPath, resultPath_ERP, resultPath_Stimulus, ...
        resultPath_Keypress, resultPath_Power, resultPath_PowerStimulus, ...
        resultPath_PowerKeypress};
    for folderIndex = 1:numel(resultFolders)
        if ~isfolder(resultFolders{folderIndex})
            mkdir(resultFolders{folderIndex});
        end
    end

    % 指定被験者の日付フォルダ、行動データ、EEGデータを取得する。
    participantFolder = fullfile(dataRoot, participant_id);
    dateFolders = dir(participantFolder);
    dateFolders = dateFolders([dateFolders.isdir] & ...
        ~ismember({dateFolders.name}, {'.', '..'}));
    if numel(dateFolders) ~= 1
        error('被験者%sの日付フォルダを一意に特定できません。', participant_id);
    end

    sessionFolder = fullfile(participantFolder, dateFolders.name);
    behaviorFolder = fullfile(sessionFolder, 'behave');
    emotivFolder = fullfile(sessionFolder, 'Emotiv');
    if ~isfolder(behaviorFolder) || ~isfolder(emotivFolder)
        error('被験者%sのbehaveまたはEmotivフォルダが見つかりません。', participant_id);
    end

    eeg_file = dir(fullfile(emotivFolder, '*.md.csv'));
    event_file = dir(fullfile(behaviorFolder, '*_events.csv'));
    if numel(eeg_file) ~= 1 || numel(event_file) ~= 1
        error('被験者%sのEEGファイルまたはevents.csvを一意に特定できません。', participant_id);
    end

    % Emotiv CSVの1行目はメタデータのため、2行目を列名として読み込む。
    EEG = readtable(fullfile(eeg_file.folder, eeg_file.name), 'NumHeaderLines', 1);
    event_log = readtable(fullfile(event_file.folder, event_file.name));
    EEG_matrix = table2array(EEG);
    EEG_time_ms = EEG.OriginalTimestamp * 1000;

    eeg_channel_names = cellfun(@(x) matlab.lang.makeValidName(['EEG.' x]), ...
        analysis_channel_labels, 'UniformOutput', false);
    eeg_variable_names = cellfun(@(x) matlab.lang.makeValidName(x), ...
        EEG.Properties.VariableNames, 'UniformOutput', false);
    [channels_found, eeg_channel_indices] = ismember(eeg_channel_names, eeg_variable_names);
    if ~all(channels_found)
        error('被験者%s: EEGチャンネルが見つかりません: %s', participant_id, ...
            strjoin(eeg_channel_names(~channels_found), ', '));
    end

    EEG_signal = EEG_matrix(:, eeg_channel_indices);
    EEG_filtered = bandstop(EEG_signal, [49 51], Fs);
    EEG_filtered = bandpass(EEG_filtered, [1 100], Fs);
    EEG_filtered = detrend(EEG_filtered);

    event_type = string(event_log.Event);
    event_detail = string(event_log.Detail);
    event_time_ms = event_log.SysUnixTime_ms_;
    n_channels = numel(eeg_channel_indices);
    power_channel_indices = 1:n_channels;

    % Block 1--6を順に解析・出力する。
    for block_index = 1:numel(block_numbers)
        blockNumber = block_numbers(block_index);

        block_file = dir(fullfile(behaviorFolder, ...
            sprintf('*block%d_results.csv', blockNumber)));
        if numel(block_file) ~= 1
            error('被験者%s: Block %dのresults.csvを一意に特定できません。', ...
                participant_id, blockNumber);
        end
        behav_block = readtable(fullfile(block_file.folder, block_file.name));

        % 刺激提示・キー押し時刻のうち、両方がそろうtrialを使用する。
        event_times = [behav_block.TiltOnsetSys_ms_, behav_block.KeyPressSys_ms_];
        event_times = event_times(~any(isnan(event_times), 2), :);
        if size(event_times, 1) ~= 320
            error('被験者%s: Block %dの有効trial数が320ではありません（%d trial）。', ...
                participant_id, blockNumber, size(event_times, 1));
        end
        stimulus_onset = event_times(:, 1);
        keypress_onset = event_times(:, 2);

        % events.csvの開始・終了時刻で連続EEGをBlockごとに抽出する。
        block_start_ms = event_time_ms(event_type == "block_start" & ...
            event_detail == string(blockNumber));
        block_end_ms = event_time_ms(event_type == "block_end" & ...
            event_detail == string(blockNumber));
        if numel(block_start_ms) ~= 1 || numel(block_end_ms) ~= 1
            error('被験者%s: events.csvからBlock %dの開始・終了時刻を一意に取得できません。', ...
                participant_id, blockNumber);
        end

        is_block = EEG_time_ms >= block_start_ms - epoch_padding_ms & ...
            EEG_time_ms <= block_end_ms + epoch_padding_ms;
        EEG_signal_block = EEG_filtered(is_block, :);
        EEG_time_ms_block = EEG_time_ms(is_block);
        fprintf('%s Block %d EEG: %d samples\n', subID, blockNumber, ...
            size(EEG_signal_block, 1));

        % 刺激提示・キー押し時刻を最も近いEEGサンプル番号へ変換する。
        stimulus_cues = interp1(EEG_time_ms_block, ...
            (1:numel(EEG_time_ms_block))', stimulus_onset, 'nearest');
        keypress_cues = interp1(EEG_time_ms_block, ...
            (1:numel(EEG_time_ms_block))', keypress_onset, 'nearest');
        all_cues = {stimulus_cues, keypress_cues};
        for cue_index = 1:numel(all_cues)
            if any(all_cues{cue_index} < -tim(1)) || ...
                    any(all_cues{cue_index} + tim(2) > size(EEG_signal_block, 1))
                error('被験者%s: Block %dでイベント前後500 ms分のEEGが不足しています。', ...
                    participant_id, blockNumber);
            end
        end

        % 次元: 時間サンプル (257) × trial (320) × EEGチャンネル (32)
        n_epoch_samples = tim(2) - tim(1);
        epoch_stimulus = zeros(n_epoch_samples, numel(stimulus_cues), n_channels);
        epoch_keypress = zeros(n_epoch_samples, numel(keypress_cues), n_channels);
        for ch = 1:n_channels
            epoch_stimulus(:, :, ch) = epoching_general( ...
                EEG_signal_block(:, ch), stimulus_cues, tim, zyn);
            epoch_keypress(:, :, ch) = epoching_general( ...
                EEG_signal_block(:, ch), keypress_cues, tim, zyn);
        end

        % ERPプロット: stimulus/keypress × 全32チャンネル
        epoch_conditions = {epoch_stimulus, epoch_keypress};
        condition_events = {'stimulus', 'keypress'};
        condition_folders = {resultPath_Stimulus, resultPath_Keypress};
        for conditionIndex = 1:numel(epoch_conditions)
            epoched_data_condition = epoch_conditions{conditionIndex};
            eventName = condition_events{conditionIndex};
            saveFolder = condition_folders{conditionIndex};

            for ch = 1:n_channels
                channelName = analysis_channel_labels{ch};
                epoched_data_channel = epoched_data_condition(:, :, ch);
                ERP = mean(epoched_data_channel, 2, 'omitnan');

                % 大量の図を画面表示するとMATLABの描画処理が滞るため、
                % 非表示で作成してファイルへ直接保存する。
                figure1 = figure('Visible', 'off', 'Position', [1 1 800 500]);
                hold on
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
                ylim([-60 60]);
                yticks(-60:30:60);
                set(gca, 'FontSize', 16);
                ylabel('Amplitude (\muV)', 'FontName', 'Arial', 'FontSize', 28);
                xlabel('Time (ms)', 'FontName', 'Arial', 'FontSize', 30);
                title(sprintf('%s - Block %d - %s - %s', ...
                    subID, blockNumber, eventName, channelName), ...
                    'FontName', 'Arial', 'FontSize', 24);
                xline(0, '--', 'Color', [0.5, 0.5, 0.5], 'LineWidth', 3);
                yline(0, '-', 'LineWidth', 1, 'Color', [0.2, 0.2, 0.2]);
                ax = gca;
                ax.LineWidth = 2;
                ax.TickDir = 'out';
                ax.FontName = 'Arial';
                set(ax, 'Box', 'off');

                saveName = sprintf('%s_Block%d_%s_%s.png', ...
                    subID, blockNumber, eventName, channelName);
                saveas(figure1, fullfile(saveFolder, saveName));
                pause(3);
                close(figure1);
            end
        end

        % パワー変化量: stimulus/keypress × 解析対象9チャンネル
        power_condition_folders = {resultPath_PowerStimulus, resultPath_PowerKeypress};
        for conditionIndex = 1:numel(epoch_conditions)
            epoched_data_condition = epoch_conditions{conditionIndex};
            eventName = condition_events{conditionIndex};
            power_change_percent = [];

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
                power_mean_trials = mean(power_all_trials, 3, 'omitnan');
                baseline_power = mean(power_mean_trials(:, baseline_indices), 2, 'omitnan');
                power_change_percent(:, :, powerChannelIndex) = ...
                    bsxfun(@rdivide, power_mean_trials, baseline_power) * 100 - 100;

                power_change_map = power_change_percent(:, :, powerChannelIndex);
                channelName = power_channel_labels{powerChannelIndex};
                % パワー図も画面には表示せず、ファイルへ直接保存する。
                figure2 = figure('Visible', 'off', 'Position', [1 1 800 500]);
                imagesc(power_time_ms, power_frequency_hz, power_change_map, [-50 50]);
                colormap('jet');
                hColorbar = colorbar;
                set(hColorbar, 'FontSize', 21, 'Ticks', -100:25:100, 'FontName', 'Arial');
                hColorbar.Label.String = 'Power change, %';
                hColorbar.Label.Rotation = 270;
                set(gca, 'YDir', 'normal', 'FontSize', 17, ...
                    'YTick', [1 10 20 30 40 50], 'XTick', -400:100:400, ...
                    'YLim', [1 50], 'XLim', [-400 400], 'FontName', 'Arial');
                ylabel('Frequency (Hz)', 'FontName', 'Arial', 'FontSize', 28);
                xlabel('Time (ms)', 'FontName', 'Arial', 'FontSize', 30);
                title(sprintf('%s - Block %d - %s - %s', ...
                    subID, blockNumber, eventName, channelName), ...
                    'FontName', 'Arial', 'FontSize', 22);
                xline(0, '--', 'Color', 'w', 'LineWidth', 2);

                saveName = sprintf('%s_Block%d_%s_%s_power.png', ...
                    subID, blockNumber, eventName, channelName);
                saveas(figure2, fullfile(power_condition_folders{conditionIndex}, saveName));
                pause(3);
                close(figure2);
            end
            fprintf('%s Block %d power calculation complete: %s\n', ...
                subID, blockNumber, eventName);
        end
    end
end
