library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity adc_mic_reader is
    port (
        clk_50m          : in  std_logic;
        rst_n            : in  std_logic;
        sample_tick      : in  std_logic;
        
        -- Interface to Altera Modular ADC IP (Standard Mode)
        cmd_valid        : out std_logic;
        cmd_channel      : out std_logic_vector(4 downto 0);
        cmd_sop          : out std_logic;
        cmd_eop          : out std_logic;
        cmd_ready        : in  std_logic;
        
        rsp_valid        : in  std_logic;
        rsp_channel      : in  std_logic_vector(4 downto 0);
        rsp_data         : in  std_logic_vector(11 downto 0);
        rsp_sop          : in  std_logic;
        rsp_eop          : in  std_logic;
        
        -- 16-bit Padded Sample Output to BRAM
        audio_sample_out : out std_logic_vector(15 downto 0)
    );
end entity adc_mic_reader;

architecture Behavioral of adc_mic_reader is
    signal latest_adc_val : std_logic_vector(11 downto 0) := (others => '0');
begin

    -- สั่งอ่าน Channel 1 (ตรงกับขา ARDUINO_ADC A0 บนบอร์ด DE10-Lite) อย่างต่อเนื่อง
    cmd_valid   <= '1';
    cmd_channel <= "00001"; -- Channel 1 = A0
    cmd_sop     <= '1';
    cmd_eop     <= '1';

    process(clk_50m, rst_n)
    begin
        if rst_n = '0' then
            latest_adc_val   <= (others => '0');
            audio_sample_out <= (others => '0');
        elsif rising_edge(clk_50m) then
            -- อัปเดตค่าล่าสุดเมื่อ ADC แปลงเสร็จ
            if rsp_valid = '1' then
                latest_adc_val <= rsp_data;
            end if;

            -- ล็อกค่าลงเอาต์พุตด้วยจังหวะ Hardware Sampling Tick 16 kHz อย่างแม่นยำ
            if sample_tick = '1' then
                audio_sample_out <= "0000" & latest_adc_val;
            end if;
        end if;
    end process;

end architecture Behavioral;