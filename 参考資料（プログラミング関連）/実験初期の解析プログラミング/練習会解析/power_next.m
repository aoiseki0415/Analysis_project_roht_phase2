function [power_data, freq, power_time_ms] = power_next(data, Fs, epoch_time_ms)
%POWER_NEXT 200 ms移動窓によるtrial別時間周波数パワーの計算
%
% 入力
%   data          : 時間点 × trial のepochデータ
%   Fs            : サンプリング周波数（Hz）
%   epoch_time_ms : dataの各行に対応する時刻（ms）
%
% 出力
%   power_data    : 周波数 × 時間窓 × trial のパワー
%   freq          : power_dataの周波数軸（Hz）
%   power_time_ms : 各移動窓の中心時刻（ms）

if nargin < 2 || isempty(Fs)
    error('サンプリング周波数 Fs を指定してください。');
end

if nargin < 3 || isempty(epoch_time_ms)
    epoch_time_ms = (0:size(data, 1)-1)' / Fs * 1000;
end

if size(data, 1) ~= numel(epoch_time_ms)
    error('dataの行数とepoch_time_msの要素数が一致しません。');
end

window_ms = 200;
window_samples = round(window_ms / 1000 * Fs);
nfft = Fs;                              % Fs=256では1 Hz刻み

if size(data, 1) < window_samples
    error('epoch長が200 msの解析窓より短いため、パワーを計算できません。');
end

window = hanning(window_samples);
n_trials = size(data, 2);
n_windows = size(data, 1) - window_samples + 1;

% pwelchの出力周波数を先に取得する。
[~, full_freq] = pwelch(data(1:window_samples, 1), window, 0, nfft, Fs);
frequency_mask = full_freq >= 1 & full_freq <= 50;
freq = full_freq(frequency_mask);

power_data = zeros(numel(freq), n_windows, n_trials);

for trial_index = 1:n_trials
    for window_index = 1:n_windows
        sample_index = window_index : window_index + window_samples - 1;
        [pxx, ~] = pwelch(data(sample_index, trial_index), ...
            window, 0, nfft, Fs);
        power_data(:, window_index, trial_index) = pxx(frequency_mask);
    end
end

window_start_index = 1:n_windows;
window_end_index = window_start_index + window_samples - 1;
power_time_ms = (epoch_time_ms(window_start_index) + ...
    epoch_time_ms(window_end_index)) / 2;

end
